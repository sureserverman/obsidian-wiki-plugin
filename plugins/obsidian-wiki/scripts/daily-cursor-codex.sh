#!/usr/bin/env bash
# daily-cursor-codex.sh — SessionStart hook for the daily Cursor/Codex
# auto-import flow.
#
# Once per UTC day (gated by the daily-cursor-codex sentinel), enqueue a
# `daily-cursor-codex` job. The drain (drain-queue.sh) then emits an
# additionalContext directive at next SessionStart instructing the agent
# to run /obsidian-wiki:scan-sessions cursor / codex and import-session
# the top candidates.
#
# This script never invokes any LLM and never writes to the vault. It only
# touches:
#   - <config>/obsidian-wiki/state/daily-daily-cursor-codex-<UTC-YYYY-MM-DD>.done
#   - <config>/obsidian-wiki/queue/daily-cursor-codex/<UTC-YYYY-MM-DD>.job
#
# Silent exit conditions (no nudge, no work):
#   - $OBSIDIAN_WIKI_NO_DAILY is set (kill switch for all daily jobs)
#   - today's daily-cursor-codex sentinel already exists

set -u  # not -e — hooks never crash the host session

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
LIB_DIR="$script_dir/lib"

# Read (and discard) hook stdin so a piped payload doesn't accumulate
cat >/dev/null 2>&1 || true

# Kill switch
[ -n "${OBSIDIAN_WIKI_NO_DAILY:-}" ] && exit 0

# shellcheck source=/dev/null
. "$LIB_DIR/queue.sh" || exit 0
# shellcheck source=/dev/null
. "$LIB_DIR/daily-gate.sh" || exit 0

# Acquire today's gate. If the gate is already closed, exit silently —
# another SessionStart already enqueued the job today.
if ! daily_gate_acquire daily-cursor-codex; then
    exit 0
fi

# Build the job body
TODAY="${DAILY_GATE_DATE:-$(date -u +%Y-%m-%d)}"
WINDOW_DAYS="${OBSIDIAN_WIKI_DAILY_WINDOW:-1}"

JOB_BODY="$(WINDOW_DAYS="$WINDOW_DAYS" TODAY="$TODAY" python3 -c "
import json, os
print(json.dumps({
    'window_days': int(os.environ.get('WINDOW_DAYS', '1') or 1),
    'tools': ['cursor', 'codex'],
    'enqueued_at_utc_date': os.environ.get('TODAY', ''),
    'schema_version': 1,
}))
" 2>/dev/null)"

if [ -z "$JOB_BODY" ]; then
    exit 0
fi

queue_write daily-cursor-codex "$TODAY" "$JOB_BODY" >/dev/null 2>&1 || true

exit 0
