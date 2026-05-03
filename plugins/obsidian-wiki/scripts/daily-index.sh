#!/usr/bin/env bash
# daily-index.sh — SessionStart hook for the daily vault-index regen flow.
#
# Once per UTC day (gated by the daily-index sentinel), enqueue a
# `daily-index` job. The drain (drain-queue.sh) then emits an
# additionalContext directive at next SessionStart instructing the agent
# to run /obsidian-wiki:index to regenerate <vault>/index.md.
#
# Per-project vault-context sidecar refresh is NOT done here — it is
# distributed to vault-context's own SessionStart hook, which gains a
# sidecar-vs-index staleness check. That naturally refreshes whichever
# project the user opens next.
#
# Silent exit conditions (no nudge, no work):
#   - $OBSIDIAN_WIKI_NO_DAILY is set
#   - today's daily-index sentinel already exists

set -u

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
LIB_DIR="$script_dir/lib"

cat >/dev/null 2>&1 || true

[ -n "${OBSIDIAN_WIKI_NO_DAILY:-}" ] && exit 0

# shellcheck source=/dev/null
. "$LIB_DIR/queue.sh" || exit 0
# shellcheck source=/dev/null
. "$LIB_DIR/daily-gate.sh" || exit 0

if ! daily_gate_acquire daily-index; then
    exit 0
fi

TODAY="${DAILY_GATE_DATE:-$(date -u +%Y-%m-%d)}"

JOB_BODY="$(TODAY="$TODAY" python3 -c "
import json, os
print(json.dumps({
    'target': 'vault-index',
    'enqueued_at_utc_date': os.environ.get('TODAY', ''),
    'schema_version': 1,
}))
" 2>/dev/null)"

if [ -z "$JOB_BODY" ]; then
    exit 0
fi

queue_write daily-index "$TODAY" "$JOB_BODY" >/dev/null 2>&1 || true

exit 0
