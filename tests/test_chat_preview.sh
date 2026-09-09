#!/usr/bin/env bash
set -eu
R="$(cd "$(dirname "$0")/.." && pwd)"; T="$(mktemp)"; trap 'rm -f "$T"' EXIT
printf '%s' '{"patches":[{"path":"Gotchas/X.md","before":"a","after":"b"}]}' >"$T"
python3 "$R/plugins/obsidian-wiki/scripts/preview-chat.py" "$T" | jq -e '.apply_authorized==false and (.digest|length)==64' >/dev/null
echo ALL OK
