#!/usr/bin/env bash
# run.sh — discover and run every tests/test_*.sh and tests/integration_*.sh.
#
# Each test script is an independent bash file that exits 0 on success and
# non-zero on failure. We invoke them in a fresh subshell so a `set -u` or
# trap from one test cannot leak into the next.

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TESTS_DIR="$ROOT/tests"

# The suite's tool floor, checked rather than assumed. A missing tool does not
# fail a test — it makes the assertions that shell out to it vacuous, and the
# suite goes green having proved nothing. That is not hypothetical: `rg` is NOT
# preinstalled on ubuntu-latest, and five tests used it, two of them for
# "private data must NOT appear here" checks written as `rg -q … && fail`, which
# cannot fire when rg exits 127. Those calls are grep now; this keeps the floor
# honest. Everything listed is present on ubuntu-latest and on a normal
# developer box — a tool outside this set belongs behind a test's own guard.
MISSING=()
for tool in bash python3 git jq flock realpath find grep; do
    command -v "$tool" >/dev/null 2>&1 || MISSING+=("$tool")
done
if [ "${#MISSING[@]}" -gt 0 ]; then
    echo "missing required tools: ${MISSING[*]}" >&2
    echo "refusing to run: tests that shell out to them would pass without asserting anything" >&2
    exit 1
fi

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
