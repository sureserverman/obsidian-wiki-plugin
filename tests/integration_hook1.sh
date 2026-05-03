#!/usr/bin/env bash
# integration_hook1.sh — end-to-end Hook 1 flow.
#
# Simulate SessionEnd → wait for the background block → simulate next
# SessionStart by running drain-queue.sh → assert the additionalContext
# advertises the just-captured session, and a second drain is silent.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$ROOT/plugins/obsidian-wiki/scripts/capture-session.sh"
DRAIN="$ROOT/plugins/obsidian-wiki/scripts/drain-queue.sh"
HIGH_FIXTURE="$ROOT/tests/fixtures/transcripts/scoring-session.jsonl"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$HOOK" ] || fail "missing hook"
[ -f "$DRAIN" ] || fail "missing drain"
[ -f "$HIGH_FIXTURE" ] || fail "missing fixture"

FAKE_CFG="$(mktemp -d)"
FAKE_VAULT="$(mktemp -d)"
PROJ="$(mktemp -d)"
trap 'rm -rf "$FAKE_CFG" "$FAKE_VAULT" "$PROJ"' EXIT

export XDG_CONFIG_HOME="$FAKE_CFG"
export HOME="$FAKE_CFG"
export OBSIDIAN_VAULT_PATH="$FAKE_VAULT"
: > "$FAKE_VAULT/log.md"
echo "# CLAUDE.md" > "$FAKE_VAULT/CLAUDE.md"

SID="e2e11111-2222-3333-4444-deadbeef9999"
PAY=$(jq -n \
    --arg sid "$SID" \
    --arg tpath "$HIGH_FIXTURE" \
    --arg cwd "$PROJ" \
    '{session_id:$sid, transcript_path:$tpath, cwd:$cwd, hook_event_name:"SessionEnd", reason:"other"}')

# Phase 1: simulate session end
printf '%s' "$PAY" | bash "$HOOK" || fail "SessionEnd hook non-zero"

# Wait up to 5s for the background block to finish writing the queue file
for _ in $(seq 1 25); do
    if [ -f "$FAKE_CFG/obsidian-wiki/queue/auto-import/e2e11111.job" ]; then
        break
    fi
    sleep 0.2
done
[ -f "$FAKE_CFG/obsidian-wiki/queue/auto-import/e2e11111.job" ] \
    || fail "queue file did not appear within 5s"
ok "SessionEnd → queue file present"

# Phase 2: simulate next SessionStart
OUT="$(: | bash "$DRAIN")" || fail "drain rc != 0"
case "$OUT" in
    *'"systemMessage":'*'1 auto-import'*) ;;
    *) fail "drain systemMessage missing or wrong: $OUT" ;;
esac
case "$OUT" in
    *"session=$SID"*) ;;
    *) fail "drain context did not list our session: $OUT" ;;
esac
ok "drain emits systemMessage + context for our session"

# Phase 3: second drain is silent
OUT2="$(: | bash "$DRAIN")"
[ -z "$OUT2" ] || fail "second drain emitted output: $OUT2"
ok "second drain is silent"

# done/ has the moved job
[ -f "$FAKE_CFG/obsidian-wiki/queue/auto-import/done/e2e11111.job" ] \
    || fail "drained job not in done/"
ok "drained job is in done/"

echo "ALL OK"
