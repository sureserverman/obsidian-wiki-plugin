#!/usr/bin/env python3
"""match-index.py — match a vault index against project signals.

Reads project signals from stdin (one normalized token per line) and a vault
`index.md` file path from argv[1]. Scores each indexed page by tag/topic/title
overlap with the signals, each matched token weighted by its rarity across the
index (`ln(N/df)`), plus a recency boost for pages that matched. Picks the top 30
matched pages with at most 5 from Plans/ and at most 8 from any other category,
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

If fewer than 5 pages match a signal token with positive weight, prints a single
line `NO_MATCHES` and exits 0.
The caller (write-context.sh) handles both cases.

Self-integration guarantee: a "Portfolio Integrations/" entry whose declaring
project is THIS repo always surfaces in the output, even if the TOP_N cap or a low
token-overlap score would otherwise drop it. The owning repo is identified by mapping
cwd to its slug via the portfolio registry (located by lib/registry_path.py) — a
definite ownership match, not fuzzy signal overlap. Best-effort: if the
registry is absent or has no entry for cwd, the guarantee is silently skipped.

Own-project guarantee: the "Projects/" page whose title or file name (the path's
stem, `Projects/<slug>.md`) equals the registry slug for cwd — else cwd's folder
name — compared without case, always surfaces too. Many project pages carry a
display title ("Alpha Widget") over a slug file name (alpha-widget.md).

Guaranteed pages are placed first and count toward TOP_N and the category caps,
so the output never exceeds either.

Pure stdlib. No third-party deps (the registry is read with a line scan, not PyYAML).
"""

import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from registry_path import registry_path  # noqa: E402

# Scoring weights
TAG_WEIGHT = 3
TOPIC_WEIGHT = 2
TITLE_WEIGHT = 1
RECENCY_BOOST = 0.5
RECENCY_DAYS = 90

# Output caps
TOP_N = 30
PLANS_CAP = 5
CATEGORY_CAP = 8
PLANS_CATEGORY = "Plans/"
PROJECTS_CATEGORY = "Projects/"
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
                    "aliases": [],
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
            elif key == "aliases":
                current_page["aliases"] = [
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
        t for t in re.split(r"[^\w-]+", title.lower()) if len(t) >= 3
    ]


def integration_slug(page: dict):
    """Declaring project slug if `page` is an integration page under Portfolio/, else None.

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

    Reads the registry `registry_path()` names and returns the `name:` of the
    project whose `path:` equals cwd. Parsed with a stdlib line scan (entries are
    `- path:` / `name:` pairs) to keep this module dependency-free. Returns None if
    the registry is absent, unreadable, or has no entry for cwd — in which case the
    self-integration guarantee is simply skipped.
    """
    try:
        text = Path(registry_path()).read_text(encoding="utf-8")
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


def page_fields(page: dict):
    """(tags, topics, title tokens, alias tokens) as lowercase token sets."""
    tags = set(page.get("tags", []))
    topics = {t.lower() for t in page.get("topics", [])}
    titles = set(title_tokens(page.get("title", "")))
    aliases = {token for alias in page.get("aliases", []) for token in title_tokens(alias)}
    return tags, topics, titles, aliases


def token_weights(pages: list, signals: set) -> dict:
    """Map each signal token to ln(N/df) over the indexed pages.

    df counts the pages whose tags, topics, title tokens or alias tokens hold the
    token. A token on every page weighs 0; a token on no page is left out (it can
    match nothing).
    """
    n = len(pages)
    df = defaultdict(int)
    for p in pages:
        for token in set().union(*page_fields(p)) & signals:
            df[token] += 1
    return {t: math.log(n / c) for t, c in df.items() if c > 0}


def score_page(page: dict, weights: dict, today: date) -> float:
    """Weighted overlap score; 0 when no token with positive weight matched.

    The recency boost is added only to pages that matched, so recency alone
    never makes a page eligible.
    """
    tags, topics, titles, aliases = page_fields(page)

    def overlap(field_set):
        return sum(weights.get(t, 0.0) for t in field_set)

    score = (TAG_WEIGHT * overlap(tags)
             + TOPIC_WEIGHT * overlap(topics)
             + TITLE_WEIGHT * overlap(titles)
             + TITLE_WEIGHT * overlap(aliases))
    if score <= 0:
        return 0.0

    updated = page.get("updated", "")
    if updated:
        try:
            d = datetime.strptime(updated, "%Y-%m-%d").date()
            if today - d <= timedelta(days=RECENCY_DAYS):
                score += RECENCY_BOOST
        except ValueError:
            pass

    return score


def category_cap(category: str) -> int:
    return PLANS_CAP if category == PLANS_CATEGORY else CATEGORY_CAP


def select(ranked: list, guaranteed: list) -> list:
    """Guaranteed pages first, then ranked pages up to TOP_N within the caps."""
    chosen = []
    seen = set()
    per_category = defaultdict(int)

    def take(p):
        chosen.append(p)
        seen.add(p["path"] or p["title"])
        per_category[p.get("category", "")] += 1

    for p in guaranteed:
        if (p["path"] or p["title"]) not in seen:
            take(p)
    for p in ranked:
        if len(chosen) >= TOP_N:
            break
        key = p["path"] or p["title"]
        cat = p.get("category", "")
        if key in seen or per_category[cat] >= category_cap(cat):
            continue
        take(p)

    chosen.sort(key=lambda p: (-p["score"], p["title"].lower()))
    return chosen


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
    weights = token_weights(pages, signals)

    all_scored = [dict(p, score=round(score_page(p, weights, today), 2)) for p in pages]
    scored = [p for p in all_scored if p["score"] > 0]

    if len(scored) < MIN_MATCHES:
        print("NO_MATCHES")
        return

    scored.sort(key=lambda p: (-p["score"], p["title"].lower()))

    # Always surface THIS repo's own integration edges and its own Projects/ page,
    # even if TOP_N, a category cap or a zero score would drop them. Integration
    # ownership is resolved from the registry (cwd -> slug), so it is a definite
    # match, not a guess; the Projects/ page falls back to cwd's folder name.
    self_slug = resolve_self_slug()
    project_name = (self_slug or os.path.basename(os.path.realpath(os.getcwd()))).lower()
    guaranteed = []
    if self_slug:
        own = next((p for p in all_scored if integration_slug(p) == self_slug), None)
        if own is not None:
            guaranteed.append(own)
    if project_name:
        def is_own(p):
            stem = os.path.splitext(os.path.basename(p.get("path", "")))[0].lower()
            return p.get("category") == PROJECTS_CATEGORY and project_name in (p["title"].lower(), stem)
        own = next((p for p in all_scored if p["title"].lower() == project_name and is_own(p)), None) \
            or next((p for p in all_scored if is_own(p)), None)
        if own is not None:
            guaranteed.append(own)

    top = select(scored, guaranteed)

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
