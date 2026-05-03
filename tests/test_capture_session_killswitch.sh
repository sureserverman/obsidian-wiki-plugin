#!/usr/bin/env bash
# test_capture_session_killswitch.sh — verify the four short-circuit gates
# in capture-session.sh ALSO suppress the new queue write (not just the log
# entry).
#
# The foreground filters in capture-session.sh:65-84 short-circuit BEFORE
# the background block runs, so a kill-switch trip means neither log entry
# nor queue file appears.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$ROOT/plugins/obsidian-wiki/scripts/capture-session.sh"
HIGH_FIXTURE="$ROOT/tests/fixtures/transcripts/scoring-session.jsonl"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$HOOK" ] || fail "capture-session.sh not at $HOOK"
[ -f "$HIGH_FIXTURE" ] || fail "high-score fixture missing"

# Helper: run the hook with a fresh cfg + vault, optional env overrides
run_with_killswitch() {
    local label="$1"; shift
    local FAKE_CFG FAKE_VAULT PROJ
    FAKE_CFG="$(mktemp -d)"
    FAKE_VAULT="$(mktemp -d)"
    PROJ="$(mktemp -d)"

    # Bootstrap vault
    : > "$FAKE_VAULT/log.md"
    echo "# CLAUDE.md" > "$FAKE_VAULT/CLAUDE.md"

    local SID="kill$RANDOM-uuid-uuid-uuid-deadbeef"
    local payload
    payload=$(jq -n \
        --arg sid "$SID" \
        --arg tpath "$HIGH_FIXTURE" \
        --arg cwd "$PROJ" \
        --arg reason "${REASON:-other}" \
        '{session_id:$sid, transcript_path:$tpath, cwd:$cwd, hook_event_name:"SessionEnd", reason:$reason}')

    XDG_CONFIG_HOME="$FAKE_CFG" \
    HOME="$FAKE_CFG" \
    OBSIDIAN_VAULT_PATH="$FAKE_VAULT" \
    OBSIDIAN_WIKI_NO_CAPTURE="${OBSIDIAN_WIKI_NO_CAPTURE:-}" \
    "$@" \
    bash "$HOOK" <<<"$payload" || fail "[$label] hook returned non-zero"

    sleep 1.5  # let any background block run

    # Assert NO queue file under any kind, NO log entry
    local NQ NL
    NQ="$(find "$FAKE_CFG/obsidian-wiki/queue" -name '*.job' 2>/dev/null | wc -l)"
    NL="$(grep -cF -e "session-capture" "$FAKE_VAULT/log.md" 2>/dev/null)"
    [ -z "$NL" ] && NL=0
    [ "$NQ" = "0" ] || fail "[$label] expected 0 queue files, found $NQ: $(find "$FAKE_CFG/obsidian-wiki/queue" -name '*.job')"
    [ "$NL" = "0" ] || fail "[$label] expected 0 log entries, found $NL: $(cat "$FAKE_VAULT/log.md")"

    # Cleanup
    rm -rf "$FAKE_CFG" "$FAKE_VAULT" "$PROJ"
    ok "[$label] no queue file, no log entry"
}

# Trip 1: OBSIDIAN_WIKI_NO_CAPTURE=1
( export OBSIDIAN_WIKI_NO_CAPTURE=1; run_with_killswitch "OBSIDIAN_WIKI_NO_CAPTURE" env )

# Trip 2: .obsidian-wiki-no-capture in cwd
# We need to seed the marker into the cwd that the payload references.
FAKE_CFG="$(mktemp -d)"
FAKE_VAULT="$(mktemp -d)"
PROJ="$(mktemp -d)"
trap 'rm -rf "$FAKE_CFG" "$FAKE_VAULT" "$PROJ"' EXIT
: > "$FAKE_VAULT/log.md"
echo "# CLAUDE.md" > "$FAKE_VAULT/CLAUDE.md"
: > "$PROJ/.obsidian-wiki-no-capture"

PAY=$(jq -n \
    --arg sid "marker11-uuid-uuid-uuid-deadbeef" \
    --arg tpath "$HIGH_FIXTURE" \
    --arg cwd "$PROJ" \
    '{session_id:$sid, transcript_path:$tpath, cwd:$cwd, hook_event_name:"SessionEnd", reason:"other"}')
XDG_CONFIG_HOME="$FAKE_CFG" HOME="$FAKE_CFG" OBSIDIAN_VAULT_PATH="$FAKE_VAULT" \
    bash "$HOOK" <<<"$PAY" || fail "[marker file] hook non-zero"
sleep 1.5
NQ=$(find "$FAKE_CFG/obsidian-wiki/queue" -name '*.job' 2>/dev/null | wc -l)
NL=$(grep -cF -e "session-capture" "$FAKE_VAULT/log.md" 2>/dev/null)
[ -z "$NL" ] && NL=0
[ "$NQ" = "0" ] || fail "[marker file] expected 0 queue files, got $NQ"
[ "$NL" = "0" ] || fail "[marker file] expected 0 log entries, got $NL"
ok "[.obsidian-wiki-no-capture marker] no queue file, no log entry"
rm -rf "$FAKE_CFG" "$FAKE_VAULT" "$PROJ"
trap - EXIT

# Trip 3: reason=clear
( export REASON=clear; run_with_killswitch "reason=clear" env )

# Trip 4: cwd inside the vault
FAKE_CFG="$(mktemp -d)"
FAKE_VAULT="$(mktemp -d)"
trap 'rm -rf "$FAKE_CFG" "$FAKE_VAULT"' EXIT
: > "$FAKE_VAULT/log.md"
echo "# CLAUDE.md" > "$FAKE_VAULT/CLAUDE.md"
mkdir -p "$FAKE_VAULT/Architecture"

PAY=$(jq -n \
    --arg sid "vault001-uuid-uuid-uuid-deadbeef" \
    --arg tpath "$HIGH_FIXTURE" \
    --arg cwd "$FAKE_VAULT/Architecture" \
    '{session_id:$sid, transcript_path:$tpath, cwd:$cwd, hook_event_name:"SessionEnd", reason:"other"}')
XDG_CONFIG_HOME="$FAKE_CFG" HOME="$FAKE_CFG" OBSIDIAN_VAULT_PATH="$FAKE_VAULT" \
    bash "$HOOK" <<<"$PAY" || fail "[cwd-in-vault] hook non-zero"
sleep 1.5
NQ=$(find "$FAKE_CFG/obsidian-wiki/queue" -name '*.job' 2>/dev/null | wc -l)
NL=$(grep -cF -e "session-capture" "$FAKE_VAULT/log.md" 2>/dev/null)
[ -z "$NL" ] && NL=0
[ "$NQ" = "0" ] || fail "[cwd-in-vault] expected 0 queue files, got $NQ"
[ "$NL" = "0" ] || fail "[cwd-in-vault] expected 0 log entries, got $NL"
ok "[cwd inside vault] no queue file, no log entry"

echo "ALL OK"
