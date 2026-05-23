#!/usr/bin/env python3
"""match-index.py — match a vault index against project signals.

Reads project signals from stdin (one normalized token per line) and a vault
`index.md` file path from argv[1]. Scores each indexed page by tag/topic/title
overlap with the signals plus a recency boost, picks the top 30 with score > 0,
groups them by category dir, and prints JSON to stdout.

Output JSON shape:
    {
      "vault_path": null,                 # set by caller via env var if needed
      "index_date": "2026-04-07",         # parsed from index.md header
      "match_count": 12,
      "matches_by_category": {
        "Gotchas/": [
          {
            "title": "DNS Leaks",
            "path": "Gotchas/DNS Leaks.md",
            "summary": "Surprising places DNS bypasses Tor.",
            "tags": ["dns", "tor"],
            "topics": ["Tor", "Pi-hole"],
            "updated": "2026-03-12",
            "score": 8.5
          },
          ...
        ],
        "Patterns/": [...]
      }
    }

If fewer than 5 pages score > 0, prints a single line `NO_MATCHES` and exits 0.
The caller (write-context.sh) handles both cases.

Self-integration guarantee: a "Portfolio Integrations/" entry whose declaring
project is THIS repo always surfaces in the output, even if the TOP_N cap or a low
token-overlap score would otherwise drop it. The owning repo is identified by mapping
cwd to its slug via ~/.claude/projects-registry.yaml (the ecosystem's source-of-truth
registry) — a definite ownership match, not fuzzy signal overlap. Best-effort: if the
registry is absent or has no entry for cwd, the guarantee is silently skipped.

Pure stdlib. No third-party deps (the registry is read with a line scan, not PyYAML).
"""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

# Scoring weights
TAG_WEIGHT = 3
TOPIC_WEIGHT = 2
TITLE_WEIGHT = 1
RECENCY_BOOST = 0.5
RECENCY_DAYS = 90

# Output cap
TOP_N = 30
MIN_MATCHES = 5

# Header regexes for parsing index.md
RE_CATEGORY = re.compile(r"^##\s+(.+?)/\s*$")
RE_PAGE = re.compile(r"^###\s+\[\[(.+?)\]\]\s*$")
RE_FIELD = re.compile(r"^-\s+(\w+):\s*(.*)$")
RE_INDEX_DATE = re.compile(r"on\s+(\d{4}-\d{2}-\d{2})")


def parse_index(path: Path):
    """Parse <vault>/index.md into a list of page records."""
    pages = []
    index_date = None
    current_category = None
    current_page = None

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")

            # Top-of-file header carries the index date
            if index_date is None:
                m = RE_INDEX_DATE.search(line)
                if m:
                    index_date = m.group(1)

            m = RE_CATEGORY.match(line)
            if m:
                if current_page is not None:
                    pages.append(current_page)
                    current_page = None
                current_category = m.group(1) + "/"
                continue

            m = RE_PAGE.match(line)
            if m:
                if current_page is not None:
                    pages.append(current_page)
                current_page = {
                    "title": m.group(1),
                    "category": current_category or "",
                    "path": "",
                    "summary": "",
                    "tags": [],
                    "topics": [],
                    "updated": "",
                }
                continue

            if current_page is None:
                continue

            m = RE_FIELD.match(line)
            if not m:
                continue
            key, value = m.group(1), m.group(2).strip()
            if key == "path":
                current_page["path"] = value
            elif key == "summary":
                current_page["summary"] = value
            elif key == "tags":
                current_page["tags"] = [
                    t.strip().lower() for t in value.split(",") if t.strip()
                ]
            elif key == "topics":
                current_page["topics"] = [
                    t.strip() for t in value.split(",") if t.strip()
                ]
            elif key == "updated":
                current_page["updated"] = value

    if current_page is not None:
        pages.append(current_page)

    return pages, index_date


def title_tokens(title: str):
    """Lowercase alphanumeric+hyphen tokens from a page title."""
    return [
        t for t in re.split(r"[^a-z0-9-]+", title.lower()) if len(t) >= 3
    ]


def integration_slug(page: dict):
    """Declaring project slug if `page` is a Portfolio integration entry, else None.

    Index path for these is `Portfolio/<area>/<slug>/integration.md`; the slug is the
    component immediately before the filename.
    """
    path = page.get("path", "")
    if not path.endswith("/integration.md"):
        return None
    parts = path.split("/")
    return parts[-2] if len(parts) >= 2 else None


def resolve_self_slug():
    """Best-effort map of the current working directory to its portfolio slug.

    Reads ~/.claude/projects-registry.yaml and returns the `name:` of the project
    whose `path:` equals cwd. Parsed with a stdlib line scan (entries are
    `- path:` / `name:` pairs) to keep this module dependency-free. Returns None if
    the registry is absent, unreadable, or has no entry for cwd — in which case the
    self-integration guarantee is simply skipped.
    """
    try:
        text = (Path.home() / ".claude" / "projects-registry.yaml").read_text(
            encoding="utf-8")
    except OSError:
        return None
    cwd = os.path.realpath(os.getcwd())
    path_cur = None
    for line in text.splitlines():
        mp = re.match(r"\s*-?\s*path:\s*(.+?)\s*$", line)
        if mp:
            path_cur = mp.group(1).strip().strip("\"'")
            continue
        mn = re.match(r"\s*name:\s*(.+?)\s*$", line)
        if mn and path_cur is not None:
            try:
                if os.path.realpath(os.path.expanduser(path_cur)) == cwd:
                    return mn.group(1).strip().strip("\"'")
            except OSError:
                pass
    return None


def score_page(page: dict, signals: set, today: date) -> float:
    score = 0.0

    # Tag overlap (weight 3)
    tag_set = set(page.get("tags", []))
    score += TAG_WEIGHT * len(tag_set & signals)

    # Topic overlap (weight 2) — case-insensitive
    topic_set = {t.lower() for t in page.get("topics", [])}
    score += TOPIC_WEIGHT * len(topic_set & signals)

    # Title-token overlap (weight 1)
    title_set = set(title_tokens(page.get("title", "")))
    score += TITLE_WEIGHT * len(title_set & signals)

    # Recency boost
    updated = page.get("updated", "")
    if updated:
        try:
            d = datetime.strptime(updated, "%Y-%m-%d").date()
            if today - d <= timedelta(days=RECENCY_DAYS):
                score += RECENCY_BOOST
        except ValueError:
            pass

    return score


def main():
    if len(sys.argv) != 2:
        sys.stderr.write("usage: match-index.py <path-to-index.md>\n")
        sys.exit(2)

    index_path = Path(sys.argv[1])
    if not index_path.is_file():
        sys.stderr.write(f"match-index: {index_path} not found\n")
        sys.exit(1)

    signals = {
        line.strip().lower()
        for line in sys.stdin
        if line.strip()
    }
    if not signals:
        print("NO_MATCHES")
        return

    pages, index_date = parse_index(index_path)
    today = date.today()

    scored = []
    for p in pages:
        s = score_page(p, signals, today)
        if s > 0:
            p_with_score = dict(p)
            p_with_score["score"] = round(s, 2)
            scored.append(p_with_score)

    if len(scored) < MIN_MATCHES:
        print("NO_MATCHES")
        return

    scored.sort(key=lambda p: (-p["score"], p["title"].lower()))
    top = scored[:TOP_N]

    # Always surface THIS repo's own integration edges, even if the TOP_N cap (or a
    # low token-overlap score) would drop them. Ownership is resolved from the
    # registry (cwd -> slug), so it is a definite match, not a guess.
    self_slug = resolve_self_slug()
    if self_slug and not any(integration_slug(p) == self_slug for p in top):
        own = next((p for p in scored if integration_slug(p) == self_slug), None)
        if own is None:
            own = next((dict(p, score=round(score_page(p, signals, today), 2))
                        for p in pages if integration_slug(p) == self_slug), None)
        if own is not None:
            top.append(own)

    by_category = defaultdict(list)
    for p in top:
        cat = p.get("category") or "Uncategorized/"
        by_category[cat].append(p)

    out = {
        "vault_path": None,
        "index_date": index_date,
        "match_count": len(top),
        "matches_by_category": dict(by_category),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
