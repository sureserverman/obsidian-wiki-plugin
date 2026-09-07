#!/usr/bin/env bash
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VALIDATE="$ROOT/plugins/obsidian-wiki/scripts/validate-vault.sh"
VAULT="$(mktemp -d)"
trap 'rm -rf "$VAULT"' EXIT

mkdir -p "$VAULT/Gotchas" "$VAULT/.obsidian-wiki/migrations/test/preimages"
printf '%s\n' '# Index' > "$VAULT/index.md"
printf '%s\n' '---' 'title: Fixture' 'created: 2026-09-07' '---' '' '# Fixture' > "$VAULT/Gotchas/fixture.md"
printf '%s\n' '[[missing target]]' > "$VAULT/.obsidian-wiki/migrations/test/preimages/fixture.md"

RESULT="$(bash "$VALIDATE" "$VAULT" --json)"
printf '%s' "$RESULT" | jq -e '.summary.errors == 0 and .summary.warnings == 0 and .summary.info == 1' >/dev/null
echo ALL OK
