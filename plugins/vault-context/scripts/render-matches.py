#!/usr/bin/env python3
"""render-matches.py — render match-index.py JSON into markdown bullets.

Reads match-index.py JSON from stdin. Writes rendered markdown to stdout
followed by two metadata lines the shell wrapper parses:

    __INDEX_DATE__:<date>
    __MATCH_COUNT__:<n>

Usage:
    render-matches.py <vault-path>

Kept as a standalone script so write-context.sh can pipe JSON into it
without the stdin/heredoc conflict that an inline `python3 - <<PY` has.
"""
import json
import os
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: render-matches.py <vault-path>", file=sys.stderr)
        return 2

    vault_path = sys.argv[1]
    data = json.loads(sys.stdin.read())

    cats = data.get("matches_by_category", {})
    if not cats:
        print("_No matches._")
        print("__INDEX_DATE__:" + str(data.get("index_date") or "(unknown)"))
        print("__MATCH_COUNT__:0")
        return 0

    lines = []
    for cat in sorted(cats.keys()):
        lines.append(f"## {cat}")
        lines.append("")
        for page in cats[cat]:
            title = page.get("title", "")
            rel = page.get("path", "")
            summary = page.get("summary", "") or "(no summary)"
            abs_path = os.path.join(vault_path, rel)
            lines.append(f"- [[{title}]] — `{abs_path}` — {summary}")
        lines.append("")

    print("\n".join(lines).rstrip())
    print("__INDEX_DATE__:" + str(data.get("index_date") or "(unknown)"))
    print("__MATCH_COUNT__:" + str(data.get("match_count", 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
