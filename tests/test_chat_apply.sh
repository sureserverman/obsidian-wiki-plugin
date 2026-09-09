#!/usr/bin/env bash
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APPLY="$ROOT/plugins/obsidian-wiki/scripts/apply-chat.py"
PROTOCOL="$ROOT/plugins/obsidian-wiki/scripts/vault-write-protocol.py"
VAULT="$(mktemp -d)"; BATCH="$(mktemp)"
trap 'rm -rf "$VAULT" "$BATCH"' EXIT

mkdir -p "$VAULT/Gotchas"
printf 'before\n' > "$VAULT/Gotchas/note.md"
BASE="$(sha256sum "$VAULT/Gotchas/note.md" | awk '{print $1}')"
python3 -c 'import hashlib,json,sys; b={"schema_version":1,"batch_id":"apply-fixture","source_id":"src_fixture","revision_id":"rev_fixture","coverage":{"total_units":0,"accounted_units":0},"claims":[],"attachments":[],"index_status":"unchanged","changes":[{"path":"Gotchas/note.md","before_sha256":sys.argv[2],"content":"after\n"}]}; b["digest"]=hashlib.sha256(json.dumps(b,sort_keys=True,separators=(",",":")).encode()).hexdigest(); json.dump(b,open(sys.argv[1],"w"))' "$BATCH" "$BASE"
DIGEST="$(jq -r .digest "$BATCH")"

WINDOW="$(python3 "$PROTOCOL" --vault "$VAULT" start --owner fixture --purpose apply-test --lease-seconds 300)"
TOKEN="$(printf '%s' "$WINDOW" | jq -r .token)"
if python3 "$APPLY" --vault "$VAULT" --allow-root Gotchas --batch "$BATCH" --accept-digest "$DIGEST" >/dev/null 2>&1; then
    echo "apply bypassed the maintenance gate" >&2
    exit 1
fi
OBSIDIAN_WIKI_MAINTENANCE_TOKEN="$TOKEN" python3 "$APPLY" --vault "$VAULT" --allow-root Gotchas --batch "$BATCH" --accept-digest "$DIGEST" | jq -e '.state == "committed" and .batch_id == "apply-fixture"' >/dev/null
[ "$(cat "$VAULT/Gotchas/note.md")" = after ]
JOURNAL="$VAULT/.obsidian-wiki/chat-journals/apply-fixture.json"
jq -e '.state == "committed" and .changes[0].before_sha256 != null' "$JOURNAL" >/dev/null
OBSIDIAN_WIKI_MAINTENANCE_TOKEN="$TOKEN" python3 "$APPLY" --vault "$VAULT" --allow-root Gotchas --batch "$BATCH" --accept-digest "$DIGEST" | jq -e '.state == "already-committed"' >/dev/null

if OBSIDIAN_WIKI_MAINTENANCE_TOKEN="$TOKEN" python3 "$APPLY" --vault "$VAULT" --allow-root Gotchas --batch "$BATCH" --accept-digest deadbeef >/dev/null 2>&1; then
    echo "wrong accepted digest was allowed" >&2
    exit 1
fi
OUTSIDE_JOURNAL="$(mktemp)"
if OBSIDIAN_WIKI_MAINTENANCE_TOKEN="$TOKEN" python3 "$APPLY" --vault "$VAULT" --recover "$OUTSIDE_JOURNAL" >/dev/null 2>&1; then
    echo "recovery accepted a journal outside the vault" >&2
    exit 1
fi
rm -f "$OUTSIDE_JOURNAL"

printf 'old\n' > "$VAULT/Gotchas/recover.md"
OLD64="$(printf old\\n | base64 -w0)"
AFTER_HASH="$(printf new\\n | sha256sum | awk '{print $1}')"
printf 'new\n' > "$VAULT/Gotchas/recover.md"
mkdir -p "$VAULT/.obsidian-wiki/chat-journals"
python3 -c 'import json,sys; json.dump({"format":1,"state":"incomplete","changes":[{"path":"Gotchas/recover.md","before_base64":sys.argv[2],"after_sha256":sys.argv[3],"applied":True}]},open(sys.argv[1],"w"))' "$VAULT/.obsidian-wiki/chat-journals/recover.json" "$OLD64" "$AFTER_HASH"
OBSIDIAN_WIKI_MAINTENANCE_TOKEN="$TOKEN" python3 "$APPLY" --vault "$VAULT" --recover "$VAULT/.obsidian-wiki/chat-journals/recover.json" | jq -e '.state == "recovered" and (.conflicts|length == 0)' >/dev/null
[ "$(cat "$VAULT/Gotchas/recover.md")" = old ]

printf 'new\n' > "$VAULT/Gotchas/recover.md"
printf 'external\n' > "$VAULT/Gotchas/recover.md"
OBSIDIAN_WIKI_MAINTENANCE_TOKEN="$TOKEN" python3 "$APPLY" --vault "$VAULT" --recover "$VAULT/.obsidian-wiki/chat-journals/recover.json" | jq -e '.state == "recovery-conflict" and .conflicts == ["Gotchas/recover.md"]' >/dev/null
[ "$(cat "$VAULT/Gotchas/recover.md")" = external ]

python3 "$PROTOCOL" --vault "$VAULT" finish --token "$TOKEN" >/dev/null
echo ALL OK
