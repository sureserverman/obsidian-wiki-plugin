#!/usr/bin/env bash
# run.sh — discover and run every tests/test_*.sh and tests/integration_*.sh.
#
# Each test script is an independent bash file that exits 0 on success and
# non-zero on failure. We invoke them in a fresh subshell so a `set -u` or
# trap from one test cannot leak into the next.

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TESTS_DIR="$ROOT/tests"

# Collect tests, sorted for determinism. Use -print0 / readarray to be
# whitespace-safe even though we do not expect spaces in test filenames.
mapfile -d '' -t FILES < <(
    {
        find "$TESTS_DIR" -maxdepth 1 -type f -name 'test_*.sh' -print0
        find "$TESTS_DIR" -maxdepth 1 -type f -name 'integration_*.sh' -print0
    } | sort -z
)

if [ "${#FILES[@]}" -eq 0 ]; then
    echo "no tests found under $TESTS_DIR"
    exit 0
fi

PASS=0
FAIL=0
FAILED_TESTS=()

for f in "${FILES[@]}"; do
    name="$(basename "$f")"
    echo "=== $name ==="
    if ( bash "$f" ); then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILED_TESTS+=("$name")
    fi
    echo
done

TOTAL=$((PASS + FAIL))
echo "================================="
echo " ran $TOTAL  pass $PASS  fail $FAIL"
if [ "$FAIL" -gt 0 ]; then
    echo " failed tests:"
    for t in "${FAILED_TESTS[@]}"; do echo "  - $t"; done
fi
echo "================================="

[ "$FAIL" -eq 0 ]
