#!/usr/bin/env bash
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROTOCOL="$ROOT/plugins/obsidian-wiki/scripts/vault-write-protocol.py"
BUILDER="$ROOT/plugins/obsidian-wiki/scripts/build-index.py"
VAULT="$(mktemp -d)"
trap 'rm -rf "$VAULT"' EXIT

mkdir -p "$VAULT/Gotchas"
printf '%s\n' '---' 'title: Writer protocol fixture' 'tags: [fixture]' '---' '' '# Writer protocol fixture' > "$VAULT/Gotchas/fixture.md"

python3 "$PROTOCOL" --vault "$VAULT" status | jq -e '.state == "open"' >/dev/null

START="$(python3 "$PROTOCOL" --vault "$VAULT" start --owner fixture-owner --purpose writer-test --lease-seconds 300)"
TOKEN="$(printf '%s' "$START" | jq -r '.token')"
[ "${#TOKEN}" -gt 20 ]
[[ "$TOKEN" == m_* ]]

if python3 "$PROTOCOL" --vault "$VAULT" check >/dev/null 2>&1; then
    echo "foreign writer was allowed" >&2
    exit 1
fi
if python3 "$PROTOCOL" --vault "$VAULT" check --token wrong >/dev/null 2>&1; then
    echo "incorrect capability was allowed" >&2
    exit 1
fi
python3 "$PROTOCOL" --vault "$VAULT" check --token "$TOKEN" | jq -e '.state == "active"' >/dev/null

if python3 "$PROTOCOL" --vault "$VAULT" start --owner second --purpose overlap --lease-seconds 300 >/dev/null 2>&1; then
    echo "overlapping maintenance window was allowed" >&2
    exit 1
fi
if python3 "$BUILDER" --vault "$VAULT" --category Gotchas >/dev/null 2>&1; then
    echo "index writer bypassed maintenance gate" >&2
    exit 1
fi
[ ! -e "$VAULT/index.md" ]
OBSIDIAN_WIKI_MAINTENANCE_TOKEN="$TOKEN" python3 "$BUILDER" --vault "$VAULT" --category Gotchas | grep -qx 'STATUS=new'
[ -f "$VAULT/index.md" ]

sed -i 's/"expires_at": ".*"/"expires_at": "2000-01-01T00:00:00Z"/' "$VAULT/.obsidian-wiki/maintenance.json"
if python3 "$PROTOCOL" --vault "$VAULT" check --token "$TOKEN" >/dev/null 2>&1; then
    echo "expired maintenance window allowed a write" >&2
    exit 1
fi
if python3 "$PROTOCOL" --vault "$VAULT" recover --owner replacement --purpose recovery --lease-seconds 300 >/dev/null 2>&1; then
    echo "stale recovery did not require acknowledgement" >&2
    exit 1
fi
RECOVERED="$(python3 "$PROTOCOL" --vault "$VAULT" recover --owner replacement --purpose recovery --lease-seconds 300 --acknowledge-stale)"
NEW_TOKEN="$(printf '%s' "$RECOVERED" | jq -r '.token')"
[[ "$NEW_TOKEN" == m_* ]]
[ "$(find "$VAULT/.obsidian-wiki/maintenance-history" -type f -name '*.json' | wc -l)" -eq 1 ]
if python3 "$PROTOCOL" --vault "$VAULT" finish --token "$TOKEN" >/dev/null 2>&1; then
    echo "stale owner finished replacement window" >&2
    exit 1
fi
python3 "$PROTOCOL" --vault "$VAULT" finish --token "$NEW_TOKEN" | jq -e '.state == "open"' >/dev/null

rg -q 'Matrix apply and recovery' "$ROOT/docs/workflows/WF-VAULT-WRITE-MAINTENANCE.md"
rg -q 'Honor exclusive maintenance' "$ROOT/plugins/obsidian-wiki/agents/vault-writer.md"
rg -q 'require_write_access' "$ROOT/plugins/obsidian-wiki/scripts/build-index.py"
echo ALL OK
