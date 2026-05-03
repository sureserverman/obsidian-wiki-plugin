#!/usr/bin/env bash
# test_capture_session_queue.sh — verify the SessionEnd hook writes both
# (a) the existing log.md session-capture entry AND (b) a new auto-import
# queue job for sessions that score >= threshold.
#
# Pipes a synthetic SessionEnd payload into capture-session.sh, then waits
# briefly for the background block to finish.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$ROOT/plugins/obsidian-wiki/scripts/capture-session.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$HOOK" ] || fail "capture-session.sh not at $HOOK"

# Isolated config + isolated vault
FAKE_CFG="$(mktemp -d)"
FAKE_VAULT="$(mktemp -d)"
trap 'rm -rf "$FAKE_CFG" "$FAKE_VAULT"' EXIT
export XDG_CONFIG_HOME="$FAKE_CFG"
export HOME="$FAKE_CFG"
export OBSIDIAN_VAULT_PATH="$FAKE_VAULT"

# Bootstrap the vault so resolve-vault.sh's gates pass
mkdir -p "$FAKE_VAULT"
: > "$FAKE_VAULT/log.md"
echo "# CLAUDE.md" > "$FAKE_VAULT/CLAUDE.md"

HIGH_FIXTURE="$ROOT/tests/fixtures/transcripts/scoring-session.jsonl"
LOW_FIXTURE="$ROOT/tests/fixtures/transcripts/low-score-session.jsonl"
[ -f "$HIGH_FIXTURE" ] || fail "high-score fixture missing at $HIGH_FIXTURE"
[ -f "$LOW_FIXTURE" ]  || fail "low-score fixture missing at $LOW_FIXTURE"

# Synthetic SessionEnd payload referencing the high-score fixture
SESSION_ID="abcd1234-aaaa-bbbb-cccc-deadbeef0001"
PROJECT_DIR="$(mktemp -d)"
cleanup_proj() { rm -rf "$PROJECT_DIR"; }
trap 'rm -rf "$FAKE_CFG" "$FAKE_VAULT" "$PROJECT_DIR"' EXIT

PAYLOAD=$(jq -n \
    --arg sid "$SESSION_ID" \
    --arg tpath "$HIGH_FIXTURE" \
    --arg cwd "$PROJECT_DIR" \
    '{session_id:$sid, transcript_path:$tpath, cwd:$cwd, hook_event_name:"SessionEnd", reason:"other"}')

# Invoke the hook
printf '%s' "$PAYLOAD" | bash "$HOOK"
RC=$?
[ "$RC" = "0" ] || fail "hook exited rc=$RC"

# Wait for the detached background block. Poll for either the queue file or
# the log entry, up to 5s, then sanity-check both.
for i in $(seq 1 25); do
    QFILE="$FAKE_CFG/obsidian-wiki/queue/auto-import/abcd1234.job"
    if [ -f "$QFILE" ] && grep -qF -e "- Session: abcd1234" "$FAKE_VAULT/log.md" 2>/dev/null; then
        break
    fi
    sleep 0.2
done

# --- Test 1: log entry --------------------------------------------------
grep -qF -e "session-capture" "$FAKE_VAULT/log.md" || fail "log.md missing session-capture entry: $(cat "$FAKE_VAULT/log.md")"
grep -qF -e "- Session: abcd1234" "$FAKE_VAULT/log.md" || fail "log.md missing short-id Session line"
ok "log.md got the session-capture entry"

# --- Test 2: queue file present with expected JSON ----------------------
QFILE="$FAKE_CFG/obsidian-wiki/queue/auto-import/abcd1234.job"
[ -f "$QFILE" ] || fail "queue file not at $QFILE (cfg tree: $(find "$FAKE_CFG" -type f 2>/dev/null))"

# Validate JSON structure
python3 -c "
import json, sys
d = json.load(open('$QFILE'))
assert d['session_id'].startswith('abcd1234'), 'session_id wrong: %r' % d['session_id']
assert d['transcript_path'] == '$HIGH_FIXTURE', 'transcript_path wrong: %r' % d['transcript_path']
assert d['cwd'] == '$PROJECT_DIR', 'cwd wrong: %r' % d['cwd']
assert d['reason'] == 'other', 'reason wrong: %r' % d['reason']
assert d['score'] >= 2, 'score below threshold: %r' % d['score']
assert d['turns'] > 0, 'turns missing: %r' % d['turns']
assert d['schema_version'] == 1, 'schema_version wrong: %r' % d['schema_version']
assert d['enqueued_at'].endswith('Z'), 'enqueued_at not UTC: %r' % d['enqueued_at']
" || fail "queue JSON validation failed"
ok "queue file present with expected JSON shape"

# --- Test 3: low-scoring session writes NEITHER log nor queue ------------
LOW_SESSION_ID="abcd9999-aaaa-bbbb-cccc-deadbeef0002"
LOW_PAYLOAD=$(jq -n \
    --arg sid "$LOW_SESSION_ID" \
    --arg tpath "$LOW_FIXTURE" \
    --arg cwd "$PROJECT_DIR" \
    '{session_id:$sid, transcript_path:$tpath, cwd:$cwd, hook_event_name:"SessionEnd", reason:"other"}')
printf '%s' "$LOW_PAYLOAD" | bash "$HOOK" || fail "low-score hook invocation failed"
sleep 1.5  # let the background block run

LOW_QFILE="$FAKE_CFG/obsidian-wiki/queue/auto-import/abcd9999.job"
[ ! -f "$LOW_QFILE" ] || fail "low-score session should not have produced a queue file"
grep -qF -e "- Session: abcd9999" "$FAKE_VAULT/log.md" \
    && fail "low-score session should not have produced a log entry"
ok "low-scoring session produces neither queue file nor log entry"

echo "ALL OK"
