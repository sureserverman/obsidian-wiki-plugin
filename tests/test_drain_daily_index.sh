#!/usr/bin/env bash
# test_drain_daily_index.sh — focused test of drain's daily-index emission.
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

queue_write daily-index 2026-05-04 \
    '{"target":"vault-index","enqueued_at_utc_date":"2026-05-04","schema_version":1}' \
    || fail "seed failed"

OUT="$(: | bash "$DRAIN")" || fail "drain rc!=0"

case "$OUT" in
    *'"systemMessage":'*'1 daily-index'*) ;;
    *) fail "systemMessage missing or wrong: $OUT" ;;
esac
ok "systemMessage announces 1 daily-index"

case "$OUT" in
    *"directive: Run /obsidian-wiki:index"*) ;;
    *) fail "index directive missing" ;;
esac
ok "directive references /obsidian-wiki:index"

case "$OUT" in
    *"target=vault-index"*) ;;
    *) fail "target line missing" ;;
esac
ok "item rendered with target field"

[ -f "$FAKE_CFG/obsidian-wiki/queue/daily-index/done/2026-05-04.job" ] \
    || fail "job not in done/"
ok "job moved to done/"

echo "ALL OK"
