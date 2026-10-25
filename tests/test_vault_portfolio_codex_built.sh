#!/usr/bin/env bash
# test_vault_portfolio_codex_built.sh — every ports/<host>/vault-portfolio (Codex, Cursor,
# OpenCode) is exactly what its sources build to for that host.
#
# Each host tree is generated from src/vault-portfolio (core/, the host's rewrites in
# hosts/<host>/host.yaml, hosts/<host>/add/ and overrides/) by the planning repo's
# build.py. This test runs that build's --check for every host tree present (by glob, so
# a host added later is checked without editing this file) when a planning checkout is
# found: $STAGED_PLANNING_ROOT, else a sibling ../staged-planning. Without one it says so
# and checks nothing, so a hand edit of a host tree is only caught where the build is
# present. (The name predates the Cursor and OpenCode trees.)
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLANNING="${STAGED_PLANNING_ROOT:-$ROOT/../staged-planning}"
BUILD="$PLANNING/build/build.py"

if [ ! -f "$BUILD" ]; then
    echo "  skip: no planning checkout with build/build.py (set STAGED_PLANNING_ROOT); the host trees are not checked"
    exit 0
fi
fails=0; n=0
for tree in "$ROOT"/ports/*/vault-portfolio; do
    [ -d "$tree" ] || continue
    host="$(basename "$(dirname "$tree")")"; n=$((n + 1))
    if out="$(cd "$ROOT" && python3 "$BUILD" --root src/vault-portfolio --host "$host" --check 2>&1)"; then
        echo "  ok: ports/$host/vault-portfolio matches its sources ($(tail -n 1 <<<"$out"))"
    else
        echo "FAIL: ports/$host/vault-portfolio does not match its sources:" >&2
        printf '%s\n' "$out" >&2
        fails=$((fails + 1))
    fi
done
[ "$n" -gt 0 ] || { echo "FAIL: no ports/<host>/vault-portfolio tree found" >&2; exit 1; }
[ "$fails" -eq 0 ] || exit 1
echo "ALL OK"
