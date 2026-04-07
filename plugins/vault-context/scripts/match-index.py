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

Pure stdlib. No third-party deps.
"""

import json
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
