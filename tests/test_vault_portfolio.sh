#!/usr/bin/env bash
# test_vault_portfolio.sh — run vault-portfolio's python suites through the one runner.
#
# vault-portfolio's tests are python files beside the code they test
# (src/vault-portfolio/core/**/tests/test-*.py). This wrapper is how tests/run.sh
# reaches them: it runs each with `python3 -I`, and fails loudly rather than
# going green on nothing — when PyYAML is missing (the scripts need it), when no
# test is found, or when any test fails.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/src/vault-portfolio/core"

if ! python3 -I -c 'import yaml' 2>/dev/null; then
    echo "FAIL: PyYAML is not importable by python3 -I; the vault-portfolio suites need it" >&2
    exit 1
fi

mapfile -d '' -t TESTS < <(find "$SRC" -path '*/tests/*' -type f -name 'test-*.py' \
    -not -path '*/fixtures/*' -print0 | sort -z)
if [ "${#TESTS[@]}" -eq 0 ]; then
    echo "FAIL: no test-*.py found under src/vault-portfolio/core" >&2
    exit 1
fi

FAILS=0
for t in "${TESTS[@]}"; do
    rel="${t#"$ROOT"/}"
    if out="$(python3 -I "$t" 2>&1)"; then
        echo "  ok: $rel"
    else
        echo "FAIL: $rel" >&2
        printf '%s\n' "$out" | tail -20 >&2
        FAILS=$((FAILS + 1))
    fi
done

echo "ran ${#TESTS[@]} vault-portfolio test file(s), $FAILS failed"
[ "$FAILS" -eq 0 ] || exit 1
echo "ALL OK"
