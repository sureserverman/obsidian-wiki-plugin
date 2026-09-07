#!/usr/bin/env bash
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APPLY="$ROOT/plugins/obsidian-wiki/scripts/apply-chat.py"
VALIDATE="$ROOT/plugins/obsidian-wiki/scripts/validate-chat.py"
PROTOCOL="$ROOT/plugins/obsidian-wiki/scripts/vault-write-protocol.py"
VAULT="$(mktemp -d)"; BATCH="$(mktemp)"; MIGRATION="$(mktemp)"
trap 'rm -rf "$VAULT" "$BATCH" "$MIGRATION"' EXIT

mkdir -p "$VAULT/Gotchas"
printf 'before\n' > "$VAULT/Gotchas/a.md"
BASE="$(sha256sum "$VAULT/Gotchas/a.md" | awk '{print $1}')"
python3 -c 'import hashlib,json,sys; b={"schema_version":1,"batch_id":"recovery-fixture","source_id":"src_fixture","revision_id":"rev_fixture","coverage":{"total_units":0,"accounted_units":0},"claims":[],"attachments":[],"index_status":"unchanged","changes":[{"path":"Gotchas/a.md","before_sha256":sys.argv[2],"content":"after\n"}]}; b["digest"]=hashlib.sha256(json.dumps(b,sort_keys=True,separators=(",",":")).encode()).hexdigest(); json.dump(b,open(sys.argv[1],"w"))' "$BATCH" "$BASE"
python3 "$VALIDATE" --batch "$BATCH" --json | jq -e '.ok == true and .mode == "batch"' >/dev/null
DIGEST="$(jq -r .digest "$BATCH")"

WINDOW="$(python3 "$PROTOCOL" --vault "$VAULT" start --owner fixture --purpose recovery-integration --lease-seconds 300)"
TOKEN="$(printf '%s' "$WINDOW" | jq -r .token)"
OBSIDIAN_WIKI_MAINTENANCE_TOKEN="$TOKEN" python3 "$APPLY" --vault "$VAULT" --allow-root Gotchas --batch "$BATCH" --accept-digest "$DIGEST" >/dev/null

printf 'before\n' > "$VAULT/Gotchas/a.md"
if OBSIDIAN_WIKI_MAINTENANCE_TOKEN="$TOKEN" python3 "$APPLY" --vault "$VAULT" --allow-root Gotchas --batch "$BATCH" --accept-digest "$DIGEST" >/dev/null 2>&1; then
    echo "changed postimage was not refused" >&2
    exit 1
fi

printf 'before-b\n' > "$VAULT/Gotchas/b.md"
printf 'before-c\n' > "$VAULT/Gotchas/c.md"
BASE_B="$(sha256sum "$VAULT/Gotchas/b.md" | awk '{print $1}')"
BASE_C="$(sha256sum "$VAULT/Gotchas/c.md" | awk '{print $1}')"
INTERRUPTED="$(mktemp)"
trap 'rm -rf "$VAULT" "$BATCH" "$MIGRATION" "$INTERRUPTED"' EXIT
python3 -c 'import hashlib,json,sys; b={"schema_version":1,"batch_id":"interrupted-fixture","source_id":"src_fixture","revision_id":"rev_fixture","coverage":{"total_units":0,"accounted_units":0},"claims":[],"attachments":[],"index_status":"unchanged","changes":[{"path":"Gotchas/b.md","before_sha256":sys.argv[2],"content":"after-b\n"},{"path":"Gotchas/c.md","before_sha256":sys.argv[3],"content":"after-c\n"}]}; b["digest"]=hashlib.sha256(json.dumps(b,sort_keys=True,separators=(",",":")).encode()).hexdigest(); json.dump(b,open(sys.argv[1],"w"))' "$INTERRUPTED" "$BASE_B" "$BASE_C"
INTERRUPTED_DIGEST="$(jq -r .digest "$INTERRUPTED")"
if OBSIDIAN_WIKI_MAINTENANCE_TOKEN="$TOKEN" OBSIDIAN_WIKI_TEST_INTERRUPT_AFTER=1 python3 "$APPLY" --vault "$VAULT" --allow-root Gotchas --batch "$INTERRUPTED" --accept-digest "$INTERRUPTED_DIGEST" >/dev/null 2>&1; then
    echo "interruption fixture completed unexpectedly" >&2
    exit 1
fi
[ "$(cat "$VAULT/Gotchas/b.md")" = after-b ]
[ "$(cat "$VAULT/Gotchas/c.md")" = before-c ]
OBSIDIAN_WIKI_MAINTENANCE_TOKEN="$TOKEN" python3 "$APPLY" --vault "$VAULT" --recover "$VAULT/.obsidian-wiki/chat-journals/interrupted-fixture.json" | jq -e '.state == "recovered"' >/dev/null
[ "$(cat "$VAULT/Gotchas/b.md")" = before-b ]
[ "$(cat "$VAULT/Gotchas/c.md")" = before-c ]

python3 -c 'import json,sys; json.dump({"schema_version":1,"migration_id":"fixture-migration","snapshot_id":"snapshot-fixture","changes":[{"path":"Sources/.keep","before_sha256":None,"after_sha256":None}]},open(sys.argv[1],"w"))' "$MIGRATION"
python3 "$VALIDATE" --migration "$MIGRATION" --json | jq -e '.ok == true and .mode == "migration"' >/dev/null
python3 -c 'import json,sys; v=json.load(open(sys.argv[1])); v["changes"][0]["path"]="../escape.md"; json.dump(v,open(sys.argv[1],"w"))' "$MIGRATION"
if python3 "$VALIDATE" --migration "$MIGRATION" --json | jq -e '.ok == false' >/dev/null; then :; else
    echo "unsafe migration path was accepted" >&2
    exit 1
fi

python3 "$PROTOCOL" --vault "$VAULT" finish --token "$TOKEN" >/dev/null
echo ALL OK
