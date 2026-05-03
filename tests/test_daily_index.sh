#!/usr/bin/env bash
# test_daily_index.sh — verify the daily-index SessionStart subhook queues
# exactly one job per UTC day and respects the kill switch.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$ROOT/plugins/obsidian-wiki/scripts/daily-index.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$HOOK" ] || fail "missing $HOOK"

FAKE_CFG="$(mktemp -d)"
trap 'rm -rf "$FAKE_CFG"' EXIT
export XDG_CONFIG_HOME="$FAKE_CFG"
export HOME="$FAKE_CFG"
export DAILY_GATE_DATE="2026-05-04"

# --- Test 1: first invocation today queues a job ---------------------------
: | bash "$HOOK" || fail "first invocation rc!=0"
JOB="$FAKE_CFG/obsidian-wiki/queue/daily-index/2026-05-04.job"
SENT="$FAKE_CFG/obsidian-wiki/state/daily-daily-index-2026-05-04.done"
[ -f "$JOB" ] || fail "expected job at $JOB"
[ -f "$SENT" ] || fail "expected sentinel at $SENT"

python3 -c "
import json
d = json.load(open('$JOB'))
assert d['target'] == 'vault-index', 'target wrong: %r' % d['target']
assert d['schema_version'] == 1
" || fail "job JSON invalid"
ok "first invocation queues job + writes sentinel"

# --- Test 2: same day no-op -----------------------------------------------
: | bash "$HOOK" || fail "second invocation rc!=0"
N="$(find "$FAKE_CFG/obsidian-wiki/queue/daily-index" -maxdepth 1 -name '*.job' 2>/dev/null | wc -l)"
[ "$N" = "1" ] || fail "second invocation produced $N jobs, expected 1"
ok "second invocation same day is no-op"

# --- Test 3: kill switch ---------------------------------------------------
rm -rf "$FAKE_CFG"; FAKE_CFG="$(mktemp -d)"
export XDG_CONFIG_HOME="$FAKE_CFG"
export HOME="$FAKE_CFG"
export DAILY_GATE_DATE="2026-05-05"
OBSIDIAN_WIKI_NO_DAILY=1 bash "$HOOK" </dev/null || fail "killswitch invocation rc!=0"
N2="$(find "$FAKE_CFG/obsidian-wiki" -name '*.job' -o -name '*.done' 2>/dev/null | wc -l)"
[ "$N2" = "0" ] || fail "killswitch should produce no files (got $N2)"
ok "OBSIDIAN_WIKI_NO_DAILY=1 → no job, no sentinel"

echo "ALL OK"
