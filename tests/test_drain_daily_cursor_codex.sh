#!/usr/bin/env bash
# test_drain_daily_cursor_codex.sh — focused test of drain's daily-cursor-codex
# emission shape.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DRAIN="$ROOT/plugins/obsidian-wiki/scripts/drain-queue.sh"
LIB="$ROOT/plugins/obsidian-wiki/scripts/lib/queue.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

FAKE_CFG="$(mktemp -d)"
trap 'rm -rf "$FAKE_CFG"' EXIT
export XDG_CONFIG_HOME="$FAKE_CFG"
export HOME="$FAKE_CFG"

# shellcheck source=/dev/null
. "$LIB"

queue_write daily-cursor-codex 2026-05-04 \
    '{"window_days":1,"tools":["cursor","codex"],"enqueued_at_utc_date":"2026-05-04","schema_version":1}' \
    || fail "seed failed"

OUT="$(: | bash "$DRAIN")" || fail "drain rc!=0"

case "$OUT" in
    *'"systemMessage":'*'1 daily-cursor-codex'*) ;;
    *) fail "systemMessage missing or wrong: $OUT" ;;
esac
ok "systemMessage announces 1 daily-cursor-codex"

case "$OUT" in
    *"directive: Run /obsidian-wiki:scan-sessions cursor"*) ;;
    *) fail "scan-sessions cursor directive missing" ;;
esac
case "$OUT" in
    *"/obsidian-wiki:scan-sessions codex"*) ;;
    *) fail "scan-sessions codex directive missing" ;;
esac
case "$OUT" in
    *"/obsidian-wiki:import-session"*) ;;
    *) fail "import-session follow-up missing in directive" ;;
esac
ok "directive references scan-sessions cursor + codex + import-session"

case "$OUT" in
    *"window_days=1"*) ;; *) fail "item missing window_days=1" ;; esac
case "$OUT" in
    *"tools=cursor,codex"*) ;; *) fail "item missing tools=cursor,codex" ;; esac
ok "item rendered with window_days + tools fields"

# Job moved to done/
[ -f "$FAKE_CFG/obsidian-wiki/queue/daily-cursor-codex/done/2026-05-04.job" ] \
    || fail "job not in done/"
ok "job moved to done/"

echo "ALL OK"
