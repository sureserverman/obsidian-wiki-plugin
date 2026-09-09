#!/usr/bin/env bash
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; V="$(mktemp -d)"; trap 'rm -rf "$V"' EXIT
mkdir -p "$V/Sources" "$V/Systems" "$V/raw/conversations/private"
printf '%s\n' 'do-not-index' > "$V/raw/conversations/private/event.json"
printf '%s\n' '---' 'title: Matrix Source' 'aliases: [Матрица, Matrix export]' 'evidence-status: participant-reported' 'verification-status: unverified' '---' '' '# Matrix Source' 'See raw/conversations/private/event.json and protected_locator_ref: secret-123.' > "$V/Sources/matrix.md"
for n in 2 3 4 5; do cp "$V/Sources/matrix.md" "$V/Sources/matrix-$n.md"; done
printf '%s\n' '---' 'title: Matrix System' 'aliases: [Matrix]' 'evidence-status: observed' 'verification-status: verified' '---' '' '# Matrix System' 'A dated system record.' > "$V/Systems/matrix.md"
python3 "$ROOT/plugins/obsidian-wiki/scripts/build-index.py" --vault "$V" --category Sources --category Systems >/dev/null
rg -q 'aliases: Матрица, Matrix export' "$V/index.md"
rg -q 'evidence-status: participant-reported' "$V/index.md"
rg -q 'verification-status: verified' "$V/index.md"
! rg -q 'raw/conversations/private|secret-123|do-not-index' "$V/index.md"
printf 'матрица\n' | python3 "$ROOT/plugins/vault-context/scripts/match-index.py" "$V/index.md" | jq -e '.match_count >= 5' >/dev/null
echo ALL OK
