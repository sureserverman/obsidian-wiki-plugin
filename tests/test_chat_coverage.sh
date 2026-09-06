#!/usr/bin/env bash
set -eu
R="$(cd "$(dirname "$0")/.." && pwd)"; T="$(mktemp)"; trap 'rm -f "$T"' EXIT
printf '%s' '{"events":[{"event_key":"ev_a"},{"event_key":"ev_a"},{"event_key":"ev_b"}]}' >"$T"
python3 "$R/plugins/obsidian-wiki/scripts/build-chat-worklist.py" "$T" | jq -e '.count==2 and (.units|length)==2' >/dev/null
echo ALL OK
