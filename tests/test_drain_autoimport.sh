#!/usr/bin/env bash
# test_drain_autoimport.sh — focused test of the drain's auto-import emission.
#
# Seeds two auto-import jobs; asserts the systemMessage line contains the
# count, the additionalContext block includes the auto-import directive
# verbatim, and both jobs end up under done/ after a single drain.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DRAIN="$ROOT/plugins/obsidian-wiki/scripts/drain-queue.sh"
LIB="$ROOT/plugins/obsidian-wiki/scripts/lib/queue.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$DRAIN" ] || fail "drain not at $DRAIN"
[ -f "$LIB" ]   || fail "queue.sh not at $LIB"

FAKE_CFG="$(mktemp -d)"
trap 'rm -rf "$FAKE_CFG"' EXIT
export XDG_CONFIG_HOME="$FAKE_CFG"
export HOME="$FAKE_CFG"

# shellcheck source=/dev/null
. "$LIB"

# Seed two auto-import jobs
queue_write auto-import job-1111 \
    '{"session_id":"job-1111-uuid","transcript_path":"/tmp/a.jsonl","cwd":"/tmp/p1","reason":"other","score":4,"turns":80,"topic":"first","enqueued_at":"2026-05-04T00:00:00Z","schema_version":1}' \
    || fail "seed 1 failed"
queue_write auto-import job-2222 \
    '{"session_id":"job-2222-uuid","transcript_path":"/tmp/b.jsonl","cwd":"/tmp/p2","reason":"logout","score":3,"turns":60,"topic":"second","enqueued_at":"2026-05-04T00:01:00Z","schema_version":1}' \
    || fail "seed 2 failed"

OUT="$(: | bash "$DRAIN")" || fail "drain non-zero"

# --- Test 1: systemMessage line carries the count ------------------------
LINE1="$(printf '%s\n' "$OUT" | head -n 1)"
case "$LINE1" in
    *'"systemMessage":'*) ;;
    *) fail "first line not systemMessage: $LINE1" ;;
esac
case "$LINE1" in
    *"2 auto-import"*) ;;
    *) fail "systemMessage missing '2 auto-import': $LINE1" ;;
esac
ok "systemMessage announces count of 2"

# --- Test 2: directive line is present, verbatim --------------------------
case "$OUT" in
    *"directive: Run /obsidian-wiki:import-session"*) ;;
    *) fail "auto-import directive missing or rewritten" ;;
esac
case "$OUT" in
    *"/obsidian-wiki:ingest"*) ;;
    *) fail "ingest follow-up not in directive" ;;
esac
ok "directive references both /obsidian-wiki:import-session and /obsidian-wiki:ingest"

# --- Test 3: both items rendered with their fields ------------------------
case "$OUT" in
    *"session=job-1111-uuid"*) ;; *) fail "job-1111 session= missing" ;; esac
case "$OUT" in
    *"session=job-2222-uuid"*) ;; *) fail "job-2222 session= missing" ;; esac
case "$OUT" in
    *"score=4"*) ;; *) fail "job-1111 score= missing" ;; esac
case "$OUT" in
    *"score=3"*) ;; *) fail "job-2222 score= missing" ;; esac
case "$OUT" in
    *"transcript=/tmp/a.jsonl"*) ;; *) fail "job-1111 transcript= missing" ;; esac
case "$OUT" in
    *"transcript=/tmp/b.jsonl"*) ;; *) fail "job-2222 transcript= missing" ;; esac
ok "both items rendered with session/score/transcript fields"

# --- Test 4: jobs moved to done/ ------------------------------------------
PEND="$(find "$FAKE_CFG/obsidian-wiki/queue/auto-import" -maxdepth 1 -name '*.job' 2>/dev/null | wc -l)"
DONE="$(find "$FAKE_CFG/obsidian-wiki/queue/auto-import/done" -maxdepth 1 -name '*.job' 2>/dev/null | wc -l)"
[ "$PEND" = "0" ] || fail "expected 0 pending after drain, got $PEND"
[ "$DONE" = "2" ] || fail "expected 2 done after drain, got $DONE"
ok "both jobs moved to done/"

echo "ALL OK"
