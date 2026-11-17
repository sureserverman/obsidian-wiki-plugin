#!/usr/bin/env bash
# test_vault_context_staleness.sh — verify vault-context's session-start
# hook handles three states correctly:
#   1. No sidecar          → emits the existing "no vault context yet" nudge
#   2. Fresh sidecar       → silent (no output)
#   3. Stale sidecar       → emits the new "stale, run /vault-context:refresh" nudge
#   4. Stale + kill switch → silent
#   5. Stack rules older than their pages → "run /vault-context:sync-rules" nudge,
#      only when no other nudge fired, and the hook writes no rule
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

rm -rf "$V4" "$P4"

# --- Stack rules -----------------------------------------------------------
SYNC="$ROOT/plugins/vault-context/scripts/sync-stack-rules.py"
STACK_MSG="Stack rules are out of date with the vault. Run /vault-context:sync-rules."
ws5="$(setup_workspace)"; V5="${ws5%|*}"; P5="${ws5#*|}"
R5="$(mktemp -d)"
trap 'rm -rf "$V5" "$P5" "$R5"' EXIT
export VAULT_CONTEXT_RULES_DIR="$R5"
mkdir -p "$P5/.claude"
touch -d '1 hour ago' "$V5/index.md"
echo "fresh" > "$P5/.claude/vault-context.md"

# 5a. No Portfolio/stacks folder in the vault → silent.
OUT="$(run_hook "$P5" "$V5")"
[ -z "$OUT" ] || fail "no stacks folder should be silent, got: $OUT"
ok "no stacks folder in the vault → silent"

# 5b. Rules in step with their pages → silent.
mkdir -p "$V5/Portfolio/stacks"
printf -- '---\nstack: alpha\npaths: ["**/*.rs"]\nsources: ["%s"]\nchecked: 2026-11-17\n---\nAlpha.\n' "$V5" \
    > "$V5/Portfolio/stacks/alpha.md"
python3 "$SYNC" --vault "$V5" --rules-dir "$R5" >/dev/null || fail "fixture sync"
OUT="$(run_hook "$P5" "$V5")"
[ -z "$OUT" ] || fail "in-sync rules should be silent, got: $OUT"
ok "rules in step with their pages → silent"

# 5c. A page newer than its rule → the stack-rules nudge, and no file changes.
printf -- '---\nstack: alpha\npaths: ["**/*.rs"]\nsources: ["%s"]\nchecked: 2026-11-17\n---\nAlpha, edited.\n' "$V5" \
    > "$V5/Portfolio/stacks/alpha.md"
before="$(cd "$R5" && find . -type f -exec sha256sum {} + | sort | sha256sum)"
OUT="$(run_hook "$P5" "$V5")"
after="$(cd "$R5" && find . -type f -exec sha256sum {} + | sort | sha256sum)"
case "$OUT" in *"$STACK_MSG"*) ;; *) fail "stack-rules nudge missing: $OUT" ;; esac
[ "$(printf '%s\n' "$OUT" | grep -c systemMessage)" -eq 1 ] || fail "more than one nudge: $OUT"
[ "$before" = "$after" ] || fail "the hook changed the rules folder"
ok "page newer than its rule → one stack-rules nudge, rules folder byte-identical"

# 5c'. The staleness kill switch silences the refresh nudge only, not this one.
touch -d '1 day ago' "$P5/.claude/vault-context.md"; touch "$V5/index.md"
OUT="$( cd "$P5" && OBSIDIAN_VAULT_PATH="$V5" VAULT_CONTEXT_NO_STALENESS_NUDGE=1 bash "$HOOK" )"
case "$OUT" in *"$STACK_MSG"*) ;; *) fail "kill switch silenced the stack-rules nudge: $OUT" ;; esac
ok "VAULT_CONTEXT_NO_STALENESS_NUDGE=1 with stale rules → the stack-rules nudge still fires"
touch -d '1 hour ago' "$V5/index.md"; touch "$P5/.claude/vault-context.md"

# 5d. A stale sidecar wins: one nudge per session, the refresh one.
touch -d '1 day ago' "$P5/.claude/vault-context.md"; touch "$V5/index.md"
OUT="$(run_hook "$P5" "$V5")"
case "$OUT" in *"/vault-context:refresh"*) ;; *) fail "refresh nudge lost beside stale rules: $OUT" ;; esac
[ "$(printf '%s\n' "$OUT" | grep -c systemMessage)" -eq 1 ] || fail "more than one nudge: $OUT"
ok "stale sidecar and stale rules → only the refresh nudge"

# 5e. No sidecar: the link nudge, alone.
rm "$P5/.claude/vault-context.md"
OUT="$(run_hook "$P5" "$V5")"
case "$OUT" in *"/vault-context:link"*) ;; *) fail "link nudge lost beside stale rules: $OUT" ;; esac
[ "$(printf '%s\n' "$OUT" | grep -c systemMessage)" -eq 1 ] || fail "more than one nudge: $OUT"
ok "no sidecar and stale rules → only the link nudge"

echo "ALL OK"
