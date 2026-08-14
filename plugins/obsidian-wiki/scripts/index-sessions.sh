#!/usr/bin/env bash
# index-sessions.sh — SessionStart hook: refresh the session index once per UTC
# day so `scan-sessions` can Read discovery results instead of shelling out.
#
# Discovery used to live in the skill, which forced eight Bash grants into its
# frontmatter — including Bash(sqlite3:*), rated HIGH (CWE-78) because the
# sqlite3 CLI's .shell/.system dot-commands execute regardless of a read-only
# database URI. Hooks are not governed by allowed-tools, so the work moves here
# and the skill keeps no shell grant at all.
#
# Writes <config>/obsidian-wiki/state/sessions-index.json. Never touches the
# vault. Silent exits: kill switch set, gate already closed today, or the
# indexer is missing.

set -u  # not -e — a hook must never crash the host session

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
LIB_DIR="$script_dir/lib"
indexer="$script_dir/index-sessions.py"

cat >/dev/null 2>&1 || true          # drain hook stdin

[ -n "${OBSIDIAN_WIKI_NO_SESSION_INDEX:-}" ] && exit 0
[ -f "$indexer" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

# shellcheck source=/dev/null
. "$LIB_DIR/daily-gate.sh" 2>/dev/null || exit 0
daily_gate_acquire session-index || exit 0

state_dir="${XDG_CONFIG_HOME:-$HOME/.config}/obsidian-wiki/state"
window="${OBSIDIAN_WIKI_INDEX_WINDOW:-14}"

# Detached: walking five session stores must never delay session start.
( nohup python3 "$indexer" --days "$window" --out "$state_dir/sessions-index.json" \
    >/dev/null 2>&1 & ) >/dev/null 2>&1
disown 2>/dev/null || true

exit 0
