#!/usr/bin/env bash
# test_vault_context_staleness.sh — verify vault-context's session-start
# hook handles three states correctly:
#   1. No sidecar          → emits the existing "no vault context yet" nudge
#   2. Fresh sidecar       → silent (no output)
#   3. Stale sidecar       → emits the new "stale, run /vault-context:refresh" nudge
#   4. Stale + kill switch → silent
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$ROOT/plugins/vault-context/scripts/session-start.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$HOOK" ] || fail "missing $HOOK"

setup_workspace() {
    local FAKE_VAULT FAKE_PROJ
    FAKE_VAULT="$(mktemp -d)"
    FAKE_PROJ="$(mktemp -d)"
    : > "$FAKE_VAULT/index.md"
    # Make $FAKE_PROJ a git repo so the gate passes
    git -C "$FAKE_PROJ" init -q
    echo "$FAKE_VAULT|$FAKE_PROJ"
}

# Helper: run the hook in a given cwd with a vault env var
run_hook() {
    local cwd="$1" vault="$2"
    ( cd "$cwd" && OBSIDIAN_VAULT_PATH="$vault" bash "$HOOK" )
}

# --- Test 1: no sidecar → "no vault context" nudge ----------------------
ws1="$(setup_workspace)"; V1="${ws1%|*}"; P1="${ws1#*|}"
trap 'rm -rf "$V1" "$P1"' EXIT
OUT1="$(run_hook "$P1" "$V1")"
case "$OUT1" in
    *"No vault context for this project yet"*) ;;
    *) fail "no-sidecar nudge missing: $OUT1" ;;
esac
case "$OUT1" in
    *"/vault-context:link"*) ;;
    *) fail "no-sidecar nudge missing :link directive: $OUT1" ;;
esac
ok "no sidecar → existing :link nudge fires"
rm -rf "$V1" "$P1"

# --- Test 2: fresh sidecar (newer than index.md) → silent ----------------
ws2="$(setup_workspace)"; V2="${ws2%|*}"; P2="${ws2#*|}"
trap 'rm -rf "$V2" "$P2"' EXIT
mkdir -p "$P2/.claude"
# Make index.md old, sidecar new
touch -d '1 hour ago' "$V2/index.md"
echo "fresh" > "$P2/.claude/vault-context.md"
OUT2="$(run_hook "$P2" "$V2")"
[ -z "$OUT2" ] || fail "fresh sidecar should be silent, got: $OUT2"
ok "fresh sidecar → silent"
rm -rf "$V2" "$P2"

# --- Test 3: stale sidecar → :refresh nudge -----------------------------
ws3="$(setup_workspace)"; V3="${ws3%|*}"; P3="${ws3#*|}"
trap 'rm -rf "$V3" "$P3"' EXIT
mkdir -p "$P3/.claude"
echo "stale" > "$P3/.claude/vault-context.md"
# Make sidecar older than index by setting sidecar mtime in the past
touch -d '1 day ago' "$P3/.claude/vault-context.md"
# Touch index to "now" to ensure it's strictly newer
touch "$V3/index.md"
OUT3="$(run_hook "$P3" "$V3")"
case "$OUT3" in
    *"Sidecar is older than the vault index"*) ;;
    *) fail "staleness nudge missing: $OUT3" ;;
esac
case "$OUT3" in
    *"/vault-context:refresh"*) ;;
    *) fail "staleness nudge missing :refresh directive: $OUT3" ;;
esac
ok "stale sidecar → :refresh nudge fires"
rm -rf "$V3" "$P3"

# --- Test 4: stale + kill switch → silent --------------------------------
ws4="$(setup_workspace)"; V4="${ws4%|*}"; P4="${ws4#*|}"
trap 'rm -rf "$V4" "$P4"' EXIT
mkdir -p "$P4/.claude"
echo "stale" > "$P4/.claude/vault-context.md"
touch -d '1 day ago' "$P4/.claude/vault-context.md"
touch "$V4/index.md"
OUT4="$( cd "$P4" && OBSIDIAN_VAULT_PATH="$V4" VAULT_CONTEXT_NO_STALENESS_NUDGE=1 bash "$HOOK" )"
[ -z "$OUT4" ] || fail "kill-switched stale sidecar should be silent, got: $OUT4"
ok "stale sidecar + VAULT_CONTEXT_NO_STALENESS_NUDGE=1 → silent"

echo "ALL OK"
