#!/usr/bin/env bash
# test_queue_lib.sh — unit tests for scripts/lib/queue.sh.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$ROOT/plugins/obsidian-wiki/scripts/lib/queue.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$LIB" ] || fail "queue.sh not at $LIB"

# Isolated config dir so we don't touch the user's real ~/.config
FAKE_CFG="$(mktemp -d)"
trap 'rm -rf "$FAKE_CFG"' EXIT
export XDG_CONFIG_HOME="$FAKE_CFG"
export HOME="$FAKE_CFG"   # belt-and-suspenders: queue_root falls back to $HOME/.config if XDG unset

# shellcheck source=/dev/null
. "$LIB"

# --- Test 1: write + presence ----------------------------------------------
queue_write auto-import sample-id '{"k":"v"}' || fail "queue_write returned non-zero"
JOB="$FAKE_CFG/obsidian-wiki/queue/auto-import/sample-id.job"
[ -f "$JOB" ] || fail "expected job file not found at $JOB"
[ "$(cat "$JOB")" = '{"k":"v"}' ] || fail "job body mismatch: $(cat "$JOB")"
ok "write creates the job with exact body"

# --- Test 2: idempotent re-write -------------------------------------------
queue_write auto-import sample-id '{"k":"DIFFERENT"}' || fail "second write failed"
[ "$(cat "$JOB")" = '{"k":"v"}' ] || fail "second write should not overwrite (body=$(cat "$JOB"))"
ok "second write with same id is a no-op"

# --- Test 3: drain --------------------------------------------------------
COUNT="$(queue_drain auto-import)"
[ "$COUNT" = "1" ] || fail "queue_drain expected count=1, got $COUNT"
[ ! -f "$JOB" ] || fail "pending job still present after drain"
[ -f "$FAKE_CFG/obsidian-wiki/queue/auto-import/done/sample-id.job" ] || fail "done file not found"
ok "drain moves pending → done and reports count"

# --- Test 4: drain of empty queue is a no-op -------------------------------
COUNT2="$(queue_drain auto-import)"
[ "$COUNT2" = "0" ] || fail "second drain expected count=0, got $COUNT2"
ok "second drain is a no-op"

# --- Test 5: queue_list returns oldest-first -------------------------------
queue_write auto-import id-1 '{"i":1}' || fail
sleep 1.05  # mtime resolution is per-second on most filesystems
queue_write auto-import id-2 '{"i":2}' || fail
LIST="$(queue_list auto-import)"
EXPECTED_FIRST="$FAKE_CFG/obsidian-wiki/queue/auto-import/id-1.job"
EXPECTED_SECOND="$FAKE_CFG/obsidian-wiki/queue/auto-import/id-2.job"
LINE1="$(printf '%s\n' "$LIST" | sed -n '1p')"
LINE2="$(printf '%s\n' "$LIST" | sed -n '2p')"
[ "$LINE1" = "$EXPECTED_FIRST" ]  || fail "list[0]=$LINE1 expected $EXPECTED_FIRST"
[ "$LINE2" = "$EXPECTED_SECOND" ] || fail "list[1]=$LINE2 expected $EXPECTED_SECOND"
ok "list is oldest-first by mtime"

# --- Test 6: concurrent writers race for one final file --------------------
# Spawn 5 background writers with the same id+different bodies.
queue_drain auto-import >/dev/null  # clear from test 5
for i in 1 2 3 4 5; do
    ( queue_write auto-import race-id "{\"who\":$i}" ) &
done
wait
RACE="$FAKE_CFG/obsidian-wiki/queue/auto-import/race-id.job"
[ -f "$RACE" ] || fail "race file not present"
# Exactly one .job (no .tmp/.lock confusion in the listing)
N="$(find "$FAKE_CFG/obsidian-wiki/queue/auto-import" -maxdepth 1 -name 'race-id.job' | wc -l)"
[ "$N" = "1" ] || fail "expected exactly 1 race-id.job, found $N"
# Body is one of the contenders, not corrupted
BODY="$(cat "$RACE")"
case "$BODY" in
    '{"who":1}'|'{"who":2}'|'{"who":3}'|'{"who":4}'|'{"who":5}') ;;
    *) fail "race body corrupted: $BODY" ;;
esac
ok "concurrent writers serialize cleanly via flock"

# --- Test 7: queue_dir auto-creates done/ ----------------------------------
[ -d "$FAKE_CFG/obsidian-wiki/queue/auto-import/done" ] || fail "done/ dir not created"
ok "queue_dir creates done/ subdir"

echo "ALL OK"
