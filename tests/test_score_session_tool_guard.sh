#!/usr/bin/env bash
# test_score_session_tool_guard.sh — score-session.py must refuse transcripts
# from tools it cannot parse instead of scoring them to a flat number.
#
# Regression: pointed at Codex rollouts, the scorer returned the same score for
# every session (no roles, no text, no is_error markers to find), which read as
# a real ranking and had to be redone by hand.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCORER="$ROOT/plugins/obsidian-wiki/scripts/score-session.py"
FIXTURES="$ROOT/tests/fixtures/transcripts"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$SCORER" ] || fail "score-session.py not at $SCORER"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- Test 1: a Claude Code transcript still scores -------------------------
out="$(python3 "$SCORER" "$FIXTURES/scoring-session.jsonl" 2>/dev/null)" \
    || fail "scorer rejected a Claude Code transcript"
case "$out" in
    *"|"*"|"*"|"*) ok "Claude Code transcript still scores ($out)" ;;
    *) fail "expected 'score|turns|topic|errors', got '$out'" ;;
esac

# --- Test 2: a Codex rollout is refused ------------------------------------
cat >"$TMP/rollout.jsonl" <<'EOF'
{"timestamp":"2026-08-12T20:12:25.406Z","ordinal":0,"type":"session_meta","payload":{"session_id":"019ff796-edd4-7911-a814-519676def646","cwd":"/home/user/dev/foo","originator":"codex-tui","thread_source":"user"}}
{"timestamp":"2026-08-12T20:12:25.407Z","ordinal":1,"type":"event_msg","payload":{"type":"task_started","turn_id":"019ff79a-cd8d-7321-a5ec-1766608478ed"}}
EOF
out="$(python3 "$SCORER" "$TMP/rollout.jsonl" 2>"$TMP/err")"
rc=$?
[ "$rc" -eq 2 ] || fail "expected exit 2 on a Codex rollout, got $rc (stdout '$out')"
[ -z "$out" ] || fail "refusal must print nothing on stdout, got '$out'"
grep -q "not a Claude Code transcript" "$TMP/err" \
    || fail "refusal message missing from stderr: $(cat "$TMP/err")"
ok "Codex rollout refused (exit 2, empty stdout, message on stderr)"

# --- Test 3: a Cursor transcript is refused --------------------------------
# Cursor puts `role` at the top level and has no `type` field.
cat >"$TMP/cursor.jsonl" <<'EOF'
{"role":"user","message":{"content":[{"type":"text","text":"why does the build fail"}]}}
{"role":"assistant","message":{"content":[{"type":"text","text":"checking the log"}]}}
EOF
if python3 "$SCORER" "$TMP/cursor.jsonl" >"$TMP/out" 2>/dev/null; then
    fail "scorer accepted a Cursor transcript (printed '$(cat "$TMP/out")')"
fi
ok "Cursor transcript refused"

# --- Test 4: the hook contract survives refusal ----------------------------
# capture-session.sh does: scored="$(python3 "$SCORER" "$T" 2>/dev/null)" || exit 0
# so a refusal must abort capture quietly, never emit a parseable score.
scored="$(python3 "$SCORER" "$TMP/rollout.jsonl" 2>/dev/null)" || scored="__aborted__"
[ "$scored" = "__aborted__" ] || fail "hook idiom did not abort; got '$scored'"
ok "capture-session.sh idiom aborts cleanly on a refused transcript"

# --- Test 5: legacy behavior preserved for empty / missing input -----------
: >"$TMP/empty.jsonl"
out="$(python3 "$SCORER" "$TMP/empty.jsonl" 2>/dev/null)" \
    || fail "empty file should not be refused (no evidence of another tool)"
[ "$out" = "0|0||0" ] || fail "empty file: expected '0|0||0', got '$out'"
ok "empty transcript keeps legacy 0|0||0 output"

out="$(python3 "$SCORER" "$TMP/does-not-exist.jsonl" 2>/dev/null)" \
    || fail "missing file should still exit 0"
[ "$out" = "0|0||0" ] || fail "missing file: expected '0|0||0', got '$out'"
ok "missing transcript keeps legacy 0|0||0 output"

# --- Test 6: a non-JSON file is not blamed on another tool -----------------
printf 'not json at all\nstill not json\n' >"$TMP/garbage.txt"
out="$(python3 "$SCORER" "$TMP/garbage.txt" 2>/dev/null)" \
    || fail "unparseable file should keep legacy behavior, not exit 2"
ok "unparseable file keeps legacy behavior ($out)"

echo "ALL OK"
