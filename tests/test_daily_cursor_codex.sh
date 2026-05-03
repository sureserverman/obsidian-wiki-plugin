#!/usr/bin/env bash
# test_daily_cursor_codex.sh — verify the daily Cursor/Codex SessionStart
# subhook queues exactly one job per UTC day and respects the kill switch.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$ROOT/plugins/obsidian-wiki/scripts/daily-cursor-codex.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$HOOK" ] || fail "missing $HOOK"

FAKE_CFG="$(mktemp -d)"
trap 'rm -rf "$FAKE_CFG"' EXIT
export XDG_CONFIG_HOME="$FAKE_CFG"
export HOME="$FAKE_CFG"
export DAILY_GATE_DATE="2026-05-04"

# --- Test 1: first invocation today queues a job and writes sentinel -----
: | bash "$HOOK" || fail "first invocation rc!=0"

JOB="$FAKE_CFG/obsidian-wiki/queue/daily-cursor-codex/2026-05-04.job"
SENTINEL="$FAKE_CFG/obsidian-wiki/state/daily-daily-cursor-codex-2026-05-04.done"
[ -f "$JOB" ] || fail "expected job at $JOB, tree: $(find "$FAKE_CFG" -type f)"
[ -f "$SENTINEL" ] || fail "expected sentinel at $SENTINEL"

# Validate JSON
python3 -c "
import json
d = json.load(open('$JOB'))
assert d['window_days'] == 1, 'window_days wrong: %r' % d['window_days']
assert d['tools'] == ['cursor','codex'], 'tools wrong: %r' % d['tools']
assert d['schema_version'] == 1, 'schema_version wrong: %r' % d['schema_version']
" || fail "job JSON invalid"
ok "first invocation queues job + writes sentinel"

# --- Test 2: second invocation same day is a no-op -----------------------
: | bash "$HOOK" || fail "second invocation rc!=0"
N="$(find "$FAKE_CFG/obsidian-wiki/queue/daily-cursor-codex" -maxdepth 1 -name '*.job' 2>/dev/null | wc -l)"
[ "$N" = "1" ] || fail "second invocation produced $N jobs, expected 1"
ok "second invocation same day is no-op"

# --- Test 3: pretend tomorrow → new job, prior sentinel pruned -----------
export DAILY_GATE_DATE="2026-05-05"
: | bash "$HOOK" || fail "next-day invocation rc!=0"
NEW_JOB="$FAKE_CFG/obsidian-wiki/queue/daily-cursor-codex/2026-05-05.job"
[ -f "$NEW_JOB" ] || fail "tomorrow job missing"
NEW_SENTINEL="$FAKE_CFG/obsidian-wiki/state/daily-daily-cursor-codex-2026-05-05.done"
[ -f "$NEW_SENTINEL" ] || fail "tomorrow sentinel missing"
[ ! -f "$SENTINEL" ] || fail "yesterday sentinel was not pruned"
ok "next-day creates new job + sentinel, prunes prior sentinel"

# --- Test 4: OBSIDIAN_WIKI_NO_DAILY=1 short-circuits ---------------------
# Fresh cfg + fresh date so the gate is open
rm -rf "$FAKE_CFG"
FAKE_CFG="$(mktemp -d)"
export XDG_CONFIG_HOME="$FAKE_CFG"
export HOME="$FAKE_CFG"
export DAILY_GATE_DATE="2026-05-06"

OBSIDIAN_WIKI_NO_DAILY=1 bash "$HOOK" </dev/null || fail "killswitch invocation rc!=0"
N2="$(find "$FAKE_CFG/obsidian-wiki" -name '*.job' 2>/dev/null | wc -l)"
S2="$(find "$FAKE_CFG/obsidian-wiki" -name '*.done' 2>/dev/null | wc -l)"
[ "$N2" = "0" ] || fail "killswitch should not produce any job (got $N2)"
[ "$S2" = "0" ] || fail "killswitch should not write any sentinel (got $S2)"
ok "OBSIDIAN_WIKI_NO_DAILY=1 → no job, no sentinel"

echo "ALL OK"
