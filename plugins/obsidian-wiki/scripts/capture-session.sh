#!/usr/bin/env bash
# capture-session.sh — SessionEnd hook for obsidian-wiki.
#
# Reads SessionEnd hook input from stdin, scores the just-ended session via
# lightweight heuristics, and (if vault-worthy) appends a `session-capture`
# entry to <vault>/log.md. The user can later review queued captures with
# `/obsidian-wiki:review-captures` and import the worthwhile ones via
# import-session.
#
# Behavior is fire-and-forget: the foreground does cheap filtering only and
# spawns a detached background subshell for the JSONL parse and log append.
# The user's session-end is never blocked. Same sync-guard + async-fetch
# pattern as check-update.sh.
#
# Silent exit conditions (no nudge, no noise):
#   - reason is "clear" (user explicitly discarded the conversation)
#   - $OBSIDIAN_WIKI_NO_CAPTURE is set, or .obsidian-wiki-no-capture exists in cwd
#   - vault not configured or <vault>/log.md missing
#   - cwd is the vault itself (don't capture vault-maintenance sessions)
#   - transcript_path is missing or unreadable
#   - the session is already captured (idempotency)
#   - score below threshold (default 2, override via $OBSIDIAN_WIKI_CAPTURE_THRESHOLD)
#
# This hook only writes to the vault's log.md. It NEVER writes to raw/, the
# wiki, or anything in the project directory where the session ran.

set -u  # don't use -e — hooks must never crash the host session

input="$(cat)"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
resolve_vault="$script_dir/resolve-vault.sh"
scorer="$script_dir/score-session.py"

# ---------------------------------------------------------------------------
# Parse a top-level field from the hook input JSON. Prefer jq; fall back to
# python3. Either returns the empty string on missing/invalid input.
# ---------------------------------------------------------------------------
parse_field() {
    local field="$1"
    if command -v jq >/dev/null 2>&1; then
        printf '%s' "$input" | jq -r ".${field} // empty" 2>/dev/null
    elif command -v python3 >/dev/null 2>&1; then
        printf '%s' "$input" | FIELD="$field" python3 -c '
import json, os, sys
try:
    d = json.load(sys.stdin)
    v = d.get(os.environ.get("FIELD", ""), "")
    print("" if v is None else v)
except Exception:
    pass
' 2>/dev/null
    fi
}

session_id="$(parse_field session_id)"
transcript_path="$(parse_field transcript_path)"
cwd_val="$(parse_field cwd)"
reason="$(parse_field reason)"

# ---------------------------------------------------------------------------
# Foreground filters — fail fast and silently. Anything that requires the
# transcript to be parsed runs in the background.
# ---------------------------------------------------------------------------
[ "$reason" = "clear" ] && exit 0
[ -n "${OBSIDIAN_WIKI_NO_CAPTURE:-}" ] && exit 0
[ -n "$cwd_val" ] && [ -f "$cwd_val/.obsidian-wiki-no-capture" ] && exit 0
[ -z "$session_id" ] && exit 0
[ -z "$transcript_path" ] && exit 0
[ -f "$transcript_path" ] || exit 0
[ -f "$resolve_vault" ] || exit 0
[ -f "$scorer" ] || exit 0

vault_path="$("$resolve_vault" 2>/dev/null)" || exit 0
[ -d "$vault_path" ] || exit 0
[ -f "$vault_path/log.md" ] || exit 0

# Skip vault-maintenance sessions: if the just-ended session ran inside the
# vault directory itself, it isn't a candidate for capture.
if [ -n "$cwd_val" ]; then
    case "$cwd_val" in
        "$vault_path"|"$vault_path"/*) exit 0 ;;
    esac
fi

threshold="${OBSIDIAN_WIKI_CAPTURE_THRESHOLD:-2}"

# ---------------------------------------------------------------------------
# Spawn the detached background scorer. Foreground returns immediately —
# the user's session-end is never blocked on JSONL parsing or disk I/O.
#
# All variables needed by the background block are baked in via single-quote
# expansion (the same pattern check-update.sh uses). The background block's
# own output is sent to /dev/null so stray messages can't leak into the
# Claude Code session.
# ---------------------------------------------------------------------------
(
    nohup bash -c '
        set -u

        SESSION_ID="'"$session_id"'"
        TRANSCRIPT="'"$transcript_path"'"
        CWD_VAL="'"$cwd_val"'"
        REASON="'"$reason"'"
        VAULT="'"$vault_path"'"
        THRESHOLD="'"$threshold"'"
        SCORER="'"$scorer"'"

        SHORT_ID="${SESSION_ID:0:8}"
        LOG="$VAULT/log.md"
        LOCK="$VAULT/log.md.lock"

        # Idempotency: an already-captured session has a `session-capture`
        # heading whose body (within the next ~10 lines) contains
        # `- Session: <short-id>`. grep -A captures that window. The
        # subsequent fgrep needs `-e` to keep the leading dash in the
        # pattern from being parsed as an option flag.
        already_captured() {
            grep -A 10 -F -e "session-capture" "$LOG" 2>/dev/null \
                | grep -qF -e "- Session: $SHORT_ID"
        }

        if already_captured; then
            exit 0
        fi

        # Score the session: output is "score|turns|topic|errors"
        scored="$(python3 "$SCORER" "$TRANSCRIPT" 2>/dev/null)" || exit 0
        [ -z "$scored" ] && exit 0

        SCORE="${scored%%|*}"
        rest="${scored#*|}"
        TURNS="${rest%%|*}"
        rest="${rest#*|}"
        TOPIC="${rest%%|*}"

        # Validate score is an integer (possibly negative)
        case "$SCORE" in
            ""|*[!0-9-]*) exit 0 ;;
        esac

        if [ "$SCORE" -lt "$THRESHOLD" ]; then
            exit 0
        fi

        if [ -z "$TOPIC" ]; then
            TOPIC="$(basename "$CWD_VAL" 2>/dev/null)"
            [ -z "$TOPIC" ] && TOPIC="(unknown)"
        fi

        TODAY="$(date -u +%Y-%m-%d)"

        ENTRY="
## [$TODAY] session-capture | $TOPIC
- Tool: claude-code
- Session: $SHORT_ID
- Transcript: $TRANSCRIPT
- Cwd: $CWD_VAL
- Score: $SCORE
- Turns: $TURNS
- Reason: $REASON
- Status: pending
"

        # Concurrent-safe append. Multiple session-ends can race; the lock
        # serializes the appends and we re-check idempotency under the lock
        # to defeat the read-then-write race window.
        (
            flock -x 9
            if ! already_captured; then
                printf "%s" "$ENTRY" >> "$LOG"
            fi
        ) 9>"$LOCK"
    ' >/dev/null 2>&1 &
) >/dev/null 2>&1
disown 2>/dev/null || true

exit 0
