#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; SCRIPT="$ROOT/plugins/obsidian-wiki/scripts/sanitize-chat.py"; TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fail(){ echo "FAIL: $*" >&2; exit 1; }; ok(){ echo "  ok: $*"; }
printf '%s\n' '{"event_id":"$private","sender":"@person:example","content":{"body":"token=secret"}}' >"$TMP/in.jsonl"
python3 "$SCRIPT" "$TMP/in.jsonl" >"$TMP/out" || fail "sanitizer failed"
rg -q '\$private|@person:example|secret' "$TMP/out" && fail "private data leaked"
jq -e '.event_key | startswith("ev_")' "$TMP/out" >/dev/null || fail "opaque key missing"
ok "sanitized event removes private identifiers"
echo "ALL OK"
