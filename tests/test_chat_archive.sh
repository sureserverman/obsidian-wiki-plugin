#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; SCRIPT="$ROOT/plugins/obsidian-wiki/scripts/import-chat.py"; TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fail(){ echo "FAIL: $*" >&2; exit 1; }; ok(){ echo "  ok: $*"; }
python3 - "$TMP/valid.zip" <<'PY'
import json, sys, zipfile
with zipfile.ZipFile(sys.argv[1], 'w') as z: z.writestr('export.json', json.dumps({'messages':[{'event_id':'$a','room_id':'!fixture:example','origin_server_ts':1,'type':'m.room.message','content':{'msgtype':'m.text','body':'hello'}}]}))
PY
python3 "$SCRIPT" "$TMP/valid.zip" --json >"$TMP/out" || fail "valid export rejected"
jq -e '.events == 1 and .source_shape == "element-export"' "$TMP/out" >/dev/null || fail "valid export inventory wrong"
ok "valid Element export inventories"
python3 - "$TMP/prep.zip" <<'PY'
import json, sys, zipfile
with zipfile.ZipFile(sys.argv[1], 'w') as z:
    z.writestr('room/export.json', json.dumps({'messages':[
        {'event_id':'$private-text','room_id':'!private:example','origin_server_ts':1,'type':'m.room.message','content':{'msgtype':'m.text','body':'token=secret'}},
        {'event_id':'$private-image','room_id':'!private:example','origin_server_ts':2,'type':'m.room.message','content':{'msgtype':'m.image','body':'screen.png','info':{'size':3}}},
        {'event_id':'$private-encrypted','room_id':'!private:example','origin_server_ts':3,'type':'m.room.encrypted','content':{}},
    ]}))
    z.writestr('room/images/screen.png', b'abc')
PY
python3 "$SCRIPT" "$TMP/prep.zip" --source-id fixture --revision-out "$TMP/revision.json" --events-out "$TMP/events.redacted.jsonl" --attachments-out "$TMP/media-manifest.json" --worklist-out "$TMP/worklist.json" --protected-map-out "$TMP/protected-map.json" --json >"$TMP/out" || fail "safe preparation was rejected"
jq -e '.events == 3 and .attachments == 1 and .unavailable_events == 1 and .attachment_mapping.candidate == 1' "$TMP/out" >/dev/null || fail "safe preparation summary wrong"
python3 "$ROOT/plugins/obsidian-wiki/scripts/validate-chat.py" --revision "$TMP/revision.json" --json | jq -e '.ok' >/dev/null || fail "prepared revision failed validation"
grep -qE '\$private|!private:example|token=secret' "$TMP/revision.json" "$TMP/events.redacted.jsonl" "$TMP/media-manifest.json" "$TMP/worklist.json" && fail "public preparation artifact leaked private data"
ok "preparation emits opaque revision and complete safe worklist"
mkdir "$TMP/vault"
mkdir "$TMP/staging"
cp "$TMP/revision.json" "$TMP/events.redacted.jsonl" "$TMP/media-manifest.json" "$TMP/worklist.json" "$TMP/protected-map.json" "$TMP/staging/"
python3 "$ROOT/plugins/obsidian-wiki/scripts/commit-chat-revision.py" --vault "$TMP/vault" --staging "$TMP/staging" --protected-root "$TMP/protected" --owner fixture >"$TMP/commit" || fail "safe revision commit failed"
jq -e '.state == "committed"' "$TMP/commit" >/dev/null || fail "safe revision commit did not return a receipt"
test -f "$TMP/vault/raw/conversations/fixture/revisions/$(jq -r .revision_id "$TMP/revision.json")/events.redacted.jsonl" || fail "safe revision event output missing from raw tree"
test -f "$TMP/protected/fixture/revisions/$(jq -r .revision_id "$TMP/revision.json")/locator-map.json" || fail "protected locator map was not separated"
test ! -e "$TMP/vault/.obsidian-wiki/maintenance.json" || fail "maintenance window was not finished"
ok "safe revision commit uses maintenance and separates protected mapping"
python3 - "$TMP/unsafe.zip" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], 'w') as z: z.writestr('../export.json', '{}')
PY
if python3 "$SCRIPT" "$TMP/unsafe.zip" --json >"$TMP/out" 2>&1; then fail "traversal member accepted"; fi
jq -e '.ok == false and (.errors|join(" ")|contains("unsafe member path"))' "$TMP/out" >/dev/null || fail "unsafe archive refusal unclear"
ok "unsafe archive is refused"
echo "ALL OK"
