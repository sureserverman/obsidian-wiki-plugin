#!/usr/bin/env bash
# integration_hook2.sh — end-to-end Hook 2 flow.
#
# Simulate two SessionStart events on the same day → only the first
# enqueues a daily-cursor-codex job. Then run the drain → assert it emits
# the cursor+codex directives. Sanity-check the daily sentinel files.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DAILY="$ROOT/plugins/obsidian-wiki/scripts/daily-cursor-codex.sh"
DRAIN="$ROOT/plugins/obsidian-wiki/scripts/drain-queue.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$DAILY" ] || fail "missing $DAILY"
[ -f "$DRAIN" ] || fail "missing $DRAIN"

FAKE_CFG="$(mktemp -d)"
trap 'rm -rf "$FAKE_CFG"' EXIT
export XDG_CONFIG_HOME="$FAKE_CFG"
export HOME="$FAKE_CFG"
export DAILY_GATE_DATE="2026-05-04"

# Two SessionStart simulations
: | bash "$DAILY" || fail "first daily rc!=0"
: | bash "$DAILY" || fail "second daily rc!=0"

# Exactly one job
N=$(find "$FAKE_CFG/obsidian-wiki/queue/daily-cursor-codex" -maxdepth 1 -name '*.job' 2>/dev/null | wc -l)
[ "$N" = "1" ] || fail "expected 1 job after two daily invocations, got $N"
ok "two daily invocations same day → 1 job (sentinel-gated)"

# Drain emits the directives
OUT="$(: | bash "$DRAIN")" || fail "drain rc!=0"
case "$OUT" in
    *"/obsidian-wiki:scan-sessions cursor"*) ;;
    *) fail "drain output missing cursor directive: $OUT" ;;
esac
case "$OUT" in
    *"/obsidian-wiki:scan-sessions codex"*) ;;
    *) fail "drain output missing codex directive: $OUT" ;;
esac
ok "drain emits cursor + codex scan-sessions directives"

echo "ALL OK"
