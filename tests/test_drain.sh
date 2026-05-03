#!/usr/bin/env bash
# test_drain.sh — unit + integration tests for scripts/drain-queue.sh.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DRAIN="$ROOT/plugins/obsidian-wiki/scripts/drain-queue.sh"
LIB="$ROOT/plugins/obsidian-wiki/scripts/lib/queue.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$DRAIN" ] || fail "drain-queue.sh not at $DRAIN"
[ -f "$LIB" ]   || fail "queue.sh not at $LIB"

FAKE_CFG="$(mktemp -d)"
trap 'rm -rf "$FAKE_CFG"' EXIT
export XDG_CONFIG_HOME="$FAKE_CFG"
export HOME="$FAKE_CFG"

# Helper to invoke the drain with empty stdin
run_drain() {
    : | bash "$DRAIN" 2>&1
}

# --- Test 1: empty queues → empty output, exit 0 ---------------------------
OUT="$(run_drain)" || fail "drain returned non-zero on empty queues (rc=$?)"
[ -z "$OUT" ] || fail "drain output non-empty on empty queues: $OUT"
ok "empty queues → silent exit"

# --- Test 2: seed one job per kind, drain emits all three sections ---------
# shellcheck source=/dev/null
. "$LIB"

queue_write auto-import abcd1234 \
    '{"session_id":"abcd1234-uuid-uuid","transcript_path":"/tmp/foo.jsonl","cwd":"/tmp/proj","score":3,"topic":"debug something","enqueued_at":"2026-05-04T00:00:00Z","schema_version":1}' \
    || fail "seed auto-import failed"
queue_write daily-cursor-codex 2026-05-04 \
    '{"window_days":1,"tools":["cursor","codex"],"enqueued_at":"2026-05-04T00:00:00Z","schema_version":1}' \
    || fail "seed daily-cursor-codex failed"
queue_write daily-index 2026-05-04 \
    '{"target":"vault-index","enqueued_at":"2026-05-04T00:00:00Z","schema_version":1}' \
    || fail "seed daily-index failed"

OUT2="$(run_drain)" || fail "drain returned non-zero on seeded queues"

# First line must be a systemMessage JSON
LINE1="$(printf '%s\n' "$OUT2" | head -n 1)"
case "$LINE1" in
    '{"systemMessage":'*) ;;
    *) fail "expected first line to be systemMessage JSON; got: $LINE1" ;;
esac
ok "first line is systemMessage JSON"

# systemMessage must mention all three kinds
case "$OUT2" in
    *"auto-import"*) ;;       *) fail "systemMessage missing auto-import" ;; esac
case "$OUT2" in
    *"daily-cursor-codex"*) ;; *) fail "systemMessage/context missing daily-cursor-codex" ;; esac
case "$OUT2" in
    *"daily-index"*) ;;        *) fail "systemMessage/context missing daily-index" ;; esac
ok "all three kinds appear in output"

# additionalContext must contain the marker line and per-kind blocks
case "$OUT2" in
    *"obsidian-wiki: pending jobs"*) ;; *) fail "context header missing" ;; esac
case "$OUT2" in
    *"kind: auto-import"*) ;; *) fail "context block for auto-import missing" ;; esac
case "$OUT2" in
    *"directive: Run /obsidian-wiki:import-session"*) ;; *) fail "auto-import directive missing" ;; esac
case "$OUT2" in
    *"directive: Run /obsidian-wiki:scan-sessions cursor"*) ;; *) fail "cursor-codex directive missing" ;; esac
case "$OUT2" in
    *"directive: Run /obsidian-wiki:index"*) ;; *) fail "index directive missing" ;; esac
ok "all three directives appear"

# Auto-import item line must include session id, score, transcript path
case "$OUT2" in
    *"session=abcd1234-uuid-uuid"*) ;; *) fail "auto-import item missing session id" ;; esac
case "$OUT2" in
    *"score=3"*) ;; *) fail "auto-import item missing score" ;; esac
case "$OUT2" in
    *"transcript=/tmp/foo.jsonl"*) ;; *) fail "auto-import item missing transcript path" ;; esac
ok "auto-import item details rendered"

# All three jobs must have moved to done/
for kind in auto-import daily-cursor-codex daily-index; do
    PEND="$(find "$FAKE_CFG/obsidian-wiki/queue/$kind" -maxdepth 1 -name '*.job' 2>/dev/null | wc -l)"
    DONE="$(find "$FAKE_CFG/obsidian-wiki/queue/$kind/done" -maxdepth 1 -name '*.job' 2>/dev/null | wc -l)"
    [ "$PEND" = "0" ] || fail "$kind: expected 0 pending after drain, got $PEND"
    [ "$DONE" = "1" ] || fail "$kind: expected 1 done after drain, got $DONE"
done
ok "all three jobs moved to done/"

# --- Test 3: re-running drain emits nothing --------------------------------
OUT3="$(run_drain)" || fail "second drain returned non-zero"
[ -z "$OUT3" ] || fail "second drain emitted output: $OUT3"
ok "second drain is silent"

echo "ALL OK"
