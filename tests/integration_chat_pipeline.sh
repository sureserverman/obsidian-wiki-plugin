#!/usr/bin/env bash
set -eu
R="$(cd "$(dirname "$0")/.." && pwd)"; V="$(mktemp -d)"; Z="$(mktemp --suffix=.zip)"; E="$(mktemp)"; B="$(mktemp)"; trap 'rm -rf "$V" "$Z" "$E" "$B"' EXIT
mkdir -p "$V/Gotchas"; printf 'old\n' > "$V/Gotchas/chat.md"
python3 -c 'import json,sys,zipfile; z=zipfile.ZipFile(sys.argv[1],"w"); z.writestr("export.json",json.dumps({"messages":[{"event_id":"fixture-event","room_id":"!fixture:example","origin_server_ts":1,"type":"m.room.message","content":{"msgtype":"m.text","body":"fixture"}}]})); z.close()' "$Z"
python3 "$R/plugins/obsidian-wiki/scripts/import-chat.py" "$Z" --json | jq -e '.ok and .events == 1' >/dev/null
printf '%s\n' '{"event_id":"fixture-event"}' > "$E"
python3 "$R/plugins/obsidian-wiki/scripts/sanitize-chat.py" "$E" | jq -e '.event_key|startswith("ev_")' >/dev/null
python3 -c 'import json,sys; json.dump({"events":[{"event_key":"ev_fixture"}]},open(sys.argv[1],"w"))' "$E"
python3 "$R/plugins/obsidian-wiki/scripts/build-chat-worklist.py" "$E" | jq -e '.count == 1' >/dev/null
python3 "$R/plugins/obsidian-wiki/scripts/review-media.py" "$E" --json | jq -e '.review_status == "manual-review-required"' >/dev/null
BASE="$(sha256sum "$V/Gotchas/chat.md" | awk '{print $1}')"
python3 -c 'import hashlib,json,sys; b={"schema_version":1,"batch_id":"pipeline","source_id":"src","revision_id":"rev","coverage":{"total_units":1,"accounted_units":1},"claims":[{"claim_id":"claim","evidence_keys":["ev_fixture"],"destinations":["Gotchas/chat.md"]}],"attachments":[],"index_status":"unchanged","changes":[{"path":"Gotchas/chat.md","before_sha256":sys.argv[2],"content":"new\n"}]}; b["digest"]=hashlib.sha256(json.dumps(b,sort_keys=True,separators=(",",":")).encode()).hexdigest(); json.dump(b,open(sys.argv[1],"w"))' "$B" "$BASE"
D="$(jq -r .digest "$B")"; W="$(python3 "$R/plugins/obsidian-wiki/scripts/vault-write-protocol.py" --vault "$V" start --owner fixture --purpose pipeline --lease-seconds 60)"; T="$(printf %s "$W"|jq -r .token)"
OBSIDIAN_WIKI_MAINTENANCE_TOKEN="$T" python3 "$R/plugins/obsidian-wiki/scripts/apply-chat.py" --vault "$V" --allow-root Gotchas --batch "$B" --accept-digest "$D" | jq -e '.state == "committed"' >/dev/null
python3 "$R/plugins/obsidian-wiki/scripts/vault-write-protocol.py" --vault "$V" finish --token "$T" >/dev/null
echo ALL OK
