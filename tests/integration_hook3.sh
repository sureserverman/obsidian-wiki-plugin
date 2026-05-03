#!/usr/bin/env bash
# integration_hook3.sh — end-to-end Hook 3 flow.
#
# Two independent flows:
#   Part A: daily-index.sh queues a job; drain emits the index nudge.
#   Part B: vault-context's session-start.sh emits the staleness nudge for
#           a project with a stale sidecar.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DAILY="$ROOT/plugins/obsidian-wiki/scripts/daily-index.sh"
DRAIN="$ROOT/plugins/obsidian-wiki/scripts/drain-queue.sh"
VC_HOOK="$ROOT/plugins/vault-context/scripts/session-start.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

# --- Part A: daily-index → drain ------------------------------------------
FAKE_CFG="$(mktemp -d)"
trap 'rm -rf "$FAKE_CFG"' EXIT
export XDG_CONFIG_HOME="$FAKE_CFG"
export HOME="$FAKE_CFG"
export DAILY_GATE_DATE="2026-05-04"

: | bash "$DAILY" || fail "daily-index rc!=0"
OUT="$(: | bash "$DRAIN")" || fail "drain rc!=0"
case "$OUT" in
    *"directive: Run /obsidian-wiki:index"*) ;;
    *) fail "drain missing index directive: $OUT" ;;
esac
ok "daily-index → drain emits /obsidian-wiki:index directive"

# --- Part B: vault-context staleness ---------------------------------------
FAKE_VAULT="$(mktemp -d)"
FAKE_PROJ="$(mktemp -d)"
trap 'rm -rf "$FAKE_CFG" "$FAKE_VAULT" "$FAKE_PROJ"' EXIT
git -C "$FAKE_PROJ" init -q
mkdir -p "$FAKE_PROJ/.claude"
echo "stale" > "$FAKE_PROJ/.claude/vault-context.md"
touch -d '1 day ago' "$FAKE_PROJ/.claude/vault-context.md"
touch "$FAKE_VAULT/index.md"

OUT2="$( cd "$FAKE_PROJ" && OBSIDIAN_VAULT_PATH="$FAKE_VAULT" bash "$VC_HOOK" )"
case "$OUT2" in
    *"Sidecar is older"*"/vault-context:refresh"*) ;;
    *) fail "vault-context staleness nudge missing: $OUT2" ;;
esac
ok "stale sidecar → vault-context :refresh nudge fires"

echo "ALL OK"
