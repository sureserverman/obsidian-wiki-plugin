#!/usr/bin/env bash
# test_capture_session_injection.sh — hook input must be data, never code.
#
# Regression: capture-session.sh built its detached background script by
# interpolating hook values into the script text —
#
#     SESSION_ID="'"$session_id"'"
#
# — which placed each value inside a double-quoted assignment in the generated
# script. Command substitution runs inside double quotes, so a `$(...)` in any
# value was executed by the background shell. `cwd` is attacker-reachable: it is
# whatever directory the user ran Claude Code in, and a directory name may
# legally contain `$( )`. Cloning a repo that creates such a directory and
# ending one session in it was arbitrary code execution.
#
# Values are now passed as positional arguments. This test asserts the payload
# does not execute AND that a normal capture still works — a script that simply
# fails to parse would also "block" the injection.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$ROOT/plugins/obsidian-wiki/scripts/capture-session.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$HOOK" ] || fail "capture-session.sh not at $HOOK"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export XDG_CONFIG_HOME="$TMP/config"

# A transcript that scores at or above the default threshold of 2, so the
# background block runs all the way to the log append.
python3 - "$TMP/transcript.jsonl" <<'PY'
import json, sys
rows = [{"type": "user", "message": {"role": "user", "content": "debug the thing"}}]
for _ in range(60):
    rows.append({"type": "assistant", "message": {"role": "assistant", "content": "x" * 20}})
    rows.append({"type": "user", "message": {"role": "user", "content": "more"}})
rows.append({"type": "assistant", "message": {"role": "assistant", "content": "y" * 900}})
open(sys.argv[1], "w").write("\n".join(json.dumps(r) for r in rows))
PY

run_hook() {  # $1 = session_id, $2 = cwd
    mkdir -p "$TMP/vault"
    : > "$TMP/vault/log.md"
    printf '{"session_id":"%s","transcript_path":"%s","cwd":"%s","reason":"other"}' \
        "$1" "$TMP/transcript.jsonl" "$2" \
        | OBSIDIAN_VAULT_PATH="$TMP/vault" bash "$HOOK" 2>"$TMP/hook.err"
    # the hook is fire-and-forget; wait for the detached child to finish
    for _ in $(seq 1 40); do
        grep -q 'session-capture' "$TMP/vault/log.md" 2>/dev/null && return 0
        sleep 0.25
    done
    return 1
}

# --- Test 1: the hook never emits shell errors on crafted input ------------
MARKER="$TMP/PWNED"
run_hook "deadbeefcafe0001" "/tmp/proj\$(touch $MARKER)" \
    || fail "capture did not complete for a crafted cwd (log never written)"
[ -s "$TMP/hook.err" ] && fail "hook wrote to stderr: $(cat "$TMP/hook.err")"
ok "crafted cwd processed without shell errors"

# --- Test 2: the payload did not execute -----------------------------------
[ -f "$MARKER" ] && fail "COMMAND INJECTION: \$(touch …) in cwd was executed"
ok "command substitution in cwd did not execute"

# --- Test 3: the value survives as literal data ----------------------------
grep -qF -e '- Cwd: /tmp/proj$(touch' "$TMP/vault/log.md" \
    || fail "crafted cwd not recorded literally: $(grep '^- Cwd:' "$TMP/vault/log.md")"
ok "crafted cwd recorded verbatim as data"

# --- Test 4: backticks are inert too ---------------------------------------
MARKER2="$TMP/PWNED2"
run_hook "deadbeefcafe0002" "/tmp/proj\`touch $MARKER2\`" \
    || fail "capture did not complete for a backtick cwd"
[ -f "$MARKER2" ] && fail "COMMAND INJECTION: backticks in cwd were executed"
ok "backtick substitution in cwd did not execute"

# --- Test 5: a normal capture is unaffected --------------------------------
# Guards against "fixing" the injection by breaking the script outright.
run_hook "deadbeefcafe0003" "/home/user/dev/normal-project" \
    || fail "a normal session was not captured — the hook is broken, not fixed"
grep -qF -e '- Cwd: /home/user/dev/normal-project' "$TMP/vault/log.md" \
    || fail "normal cwd missing from the log entry"
grep -qF -e '- Session: deadbeef' "$TMP/vault/log.md" \
    || fail "short-id missing from the log entry"
ok "a normal session still captures correctly"

echo "ALL OK"
