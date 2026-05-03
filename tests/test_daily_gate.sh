#!/usr/bin/env bash
# test_daily_gate.sh — unit tests for scripts/lib/daily-gate.sh.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$ROOT/plugins/obsidian-wiki/scripts/lib/daily-gate.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$LIB" ] || fail "daily-gate.sh not at $LIB"

FAKE_CFG="$(mktemp -d)"
trap 'rm -rf "$FAKE_CFG"' EXIT
export XDG_CONFIG_HOME="$FAKE_CFG"
export HOME="$FAKE_CFG"

# shellcheck source=/dev/null
. "$LIB"

# Pin the date for deterministic tests
export DAILY_GATE_DATE="2026-05-04"

# --- Test 1: status open before any acquire --------------------------------
S="$(daily_gate_status daily-cursor-codex)"
[ "$S" = "open" ] || fail "status before acquire: expected 'open' got '$S'"
ok "fresh kind reports status=open"

# --- Test 2: first acquire returns 0, creates sentinel ---------------------
daily_gate_acquire daily-cursor-codex || fail "first acquire returned non-zero"
SENTINEL="$FAKE_CFG/obsidian-wiki/state/daily-daily-cursor-codex-2026-05-04.done"
[ -f "$SENTINEL" ] || fail "sentinel not created at $SENTINEL"
ok "first acquire returns 0 and writes sentinel"

# --- Test 3: status closed after acquire -----------------------------------
S2="$(daily_gate_status daily-cursor-codex)"
[ "$S2" = "closed" ] || fail "status after acquire: expected 'closed' got '$S2'"
ok "after acquire, status=closed"

# --- Test 4: second acquire same day returns 1, sentinel still there ------
if daily_gate_acquire daily-cursor-codex; then
    fail "second acquire same day should have returned 1"
fi
[ -f "$SENTINEL" ] || fail "sentinel disappeared after no-op acquire"
ok "second acquire same day returns 1, sentinel preserved"

# --- Test 5: pretend it's tomorrow → acquire returns 0, prunes yesterday ---
export DAILY_GATE_DATE="2026-05-05"
daily_gate_acquire daily-cursor-codex || fail "next-day acquire returned non-zero"
NEW_SENTINEL="$FAKE_CFG/obsidian-wiki/state/daily-daily-cursor-codex-2026-05-05.done"
[ -f "$NEW_SENTINEL" ] || fail "new-day sentinel not at $NEW_SENTINEL"
[ ! -f "$SENTINEL" ]  || fail "yesterday sentinel was not pruned (still at $SENTINEL)"
ok "next-day acquire creates new sentinel and prunes the prior one"

# --- Test 6: different kinds are independent -------------------------------
daily_gate_acquire daily-index || fail "daily-index first acquire failed"
S3="$(daily_gate_status daily-cursor-codex)"
S4="$(daily_gate_status daily-index)"
[ "$S3" = "closed" ] || fail "daily-cursor-codex should still be closed (got $S3)"
[ "$S4" = "closed" ] || fail "daily-index should be closed (got $S4)"
# Pruning daily-index should NOT affect daily-cursor-codex sentinels (different kind)
[ -f "$NEW_SENTINEL" ] || fail "daily-cursor-codex 2026-05-05 sentinel got pruned by daily-index acquire"
ok "kinds are isolated; cross-kind acquire does not prune"

echo "ALL OK"
