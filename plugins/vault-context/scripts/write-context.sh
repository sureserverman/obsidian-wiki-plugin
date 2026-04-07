#!/usr/bin/env bash
# write-context.sh — render the vault-context sidecar from match-index.py output.
#
# Usage:
#   write-context.sh <project-name> <vault-path> [<output-file>]
#
# Reads match-index.py JSON (or the literal string `NO_MATCHES`) from stdin and
# writes the rendered sidecar to <output-file> (default: $PWD/.claude/vault-context.md).
#
# Renders matches grouped by category from the template at
# ${CLAUDE_PLUGIN_ROOT}/assets/vault-context-template.md.
#
# Pure shell + python3 stdlib. No third-party deps.

set -euo pipefail

if [ $# -lt 2 ]; then
    printf 'usage: write-context.sh <project-name> <vault-path> [<output-file>]\n' >&2
    exit 2
fi

project_name="$1"
vault_path="$2"
output_file="${3:-$PWD/.claude/vault-context.md}"

if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    # Fall back to script's own directory's parent so the script is testable
    # outside Claude Code's environment.
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    CLAUDE_PLUGIN_ROOT="$(dirname "$script_dir")"
fi

template="$CLAUDE_PLUGIN_ROOT/assets/vault-context-template.md"
if [ ! -f "$template" ]; then
    printf 'write-context: template missing at %s\n' "$template" >&2
    exit 1
fi

today="$(date -u +%Y-%m-%d)"
mkdir -p "$(dirname "$output_file")"

# Read all of stdin once
stdin_content="$(cat)"

if [ "$(printf '%s' "$stdin_content" | head -n 1)" = "NO_MATCHES" ]; then
    # Render an empty sidecar so the SessionStart hook stops prompting
    body="_No vault pages currently match this project. Run \`/obsidian-wiki:index\` from the vault if you've added new pages, then \`/vault-context:refresh\`._"
    index_date="(none)"
    match_count="0"
else
    # Parse JSON and render markdown bullets, grouped by category
    rendered="$(printf '%s' "$stdin_content" | python3 - "$vault_path" <<'PY'
import json, os, sys

vault_path = sys.argv[1]
data = json.loads(sys.stdin.read())

cats = data.get("matches_by_category", {})
if not cats:
    print("_No matches._")
    print("__INDEX_DATE__:" + str(data.get("index_date") or "(unknown)"))
    print("__MATCH_COUNT__:0")
    sys.exit(0)

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
PY
)"

    # Split body from metadata footer
    body="$(printf '%s\n' "$rendered" | sed -E '/^__INDEX_DATE__:/,$d')"
    index_date="$(printf '%s\n' "$rendered" | sed -nE 's/^__INDEX_DATE__:(.*)/\1/p')"
    match_count="$(printf '%s\n' "$rendered" | sed -nE 's/^__MATCH_COUNT__:(.*)/\1/p')"
fi

# Substitute into the template using a temp file (no `sed -i` quoting headaches)
tmpfile="$(mktemp)"
trap 'rm -f "$tmpfile"' EXIT

awk -v proj="$project_name" \
    -v dt="$today" \
    -v vp="$vault_path" \
    -v idate="$index_date" \
    -v mcount="$match_count" \
    -v body="$body" '
{
    gsub(/<PROJECT_NAME>/, proj)
    gsub(/<DATE>/, dt)
    gsub(/<VAULT_PATH>/, vp)
    gsub(/<INDEX_DATE>/, idate)
    gsub(/<MATCH_COUNT>/, mcount)
    gsub(/<MATCHES_GROUPED_BY_CATEGORY>/, body)
    print
}
' "$template" > "$tmpfile"

mv "$tmpfile" "$output_file"
trap - EXIT

printf 'wrote %s\n' "$output_file"
