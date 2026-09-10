#!/usr/bin/env bash
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILDER="$ROOT/plugins/obsidian-wiki/scripts/build-index.py"
VAULT="$(mktemp -d)"
trap 'rm -rf "$VAULT"' EXIT

mkdir -p "$VAULT/Gotchas" "$VAULT/Sources"
printf '%s\n' '---' 'title: Fixture' 'created: 2026-09-07' '---' '' '# Fixture' > "$VAULT/Gotchas/fixture.md"
python3 "$BUILDER" --vault "$VAULT" --category Gotchas --category Sources >/dev/null
grep -qxF '## Sources/' "$VAULT/index.md"
echo ALL OK
