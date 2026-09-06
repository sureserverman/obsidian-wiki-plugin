#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; SCRIPT="$ROOT/plugins/obsidian-wiki/scripts/import-chat.py"; TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fail(){ echo "FAIL: $*" >&2; exit 1; }; ok(){ echo "  ok: $*"; }
python3 - "$TMP/valid.zip" <<'PY'
import json, sys, zipfile
with zipfile.ZipFile(sys.argv[1], 'w') as z: z.writestr('export.json', json.dumps({'messages':[{'event_id':'$a','origin_server_ts':1,'type':'m.room.message','content':{'msgtype':'m.text','body':'hello'}}]}))
PY
python3 "$SCRIPT" "$TMP/valid.zip" --json >"$TMP/out" || fail "valid export rejected"
jq -e '.events == 1 and .source_shape == "element-export"' "$TMP/out" >/dev/null || fail "valid export inventory wrong"
ok "valid Element export inventories"
python3 - "$TMP/unsafe.zip" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], 'w') as z: z.writestr('../export.json', '{}')
PY
if python3 "$SCRIPT" "$TMP/unsafe.zip" --json >"$TMP/out" 2>&1; then fail "traversal member accepted"; fi
jq -e '.ok == false and (.errors|join(" ")|contains("unsafe member path"))' "$TMP/out" >/dev/null || fail "unsafe archive refusal unclear"
ok "unsafe archive is refused"
echo "ALL OK"
