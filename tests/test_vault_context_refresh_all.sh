#!/usr/bin/env bash
# test_vault_context_refresh_all.sh — refresh-all.sh regenerates the sidecar of every
# registered project that already has one, and of no other directory.
#
# Fixture registry: alpha and beta are linked (sidecar present), gamma is not,
# area/ is a registered grouping folder holding area/child, and gone/ is registered
# but missing. Every case runs against fixtures (vault, registry), so the test says
# nothing about the machine it runs on.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOL="$ROOT/plugins/vault-context/scripts/refresh-all.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$TOOL" ] || fail "missing $TOOL"

WORK="$(mktemp -d)"
trap 'chmod -R u+w "$WORK" 2>/dev/null; rm -rf "$WORK"' EXIT
V="$WORK/vault"; P="$WORK/p"
mkdir -p "$V" "$P/area"
printf '%s\n' "# Index generated on 2026-11-17" "" "## Gotchas/" "" \
    "### [[Fixture Page]]" "- path: Gotchas/Fixture Page.md" "- summary: s" "- tags: alpha" > "$V/index.md"

for p in alpha beta gamma area/child; do
    mkdir -p "$P/$p"; git -C "$P/$p" init -q
    echo "# $p" > "$P/$p/README.md"
done
for p in alpha beta; do
    mkdir -p "$P/$p/.claude"
    echo "old sidecar for $p" > "$P/$p/.claude/vault-context.md"
done
echo "old sidecar for the area" > "$P/area/vault-context.md.keep"

{
    echo "version: 1"; echo "projects:"
    for p in alpha beta gamma area area/child gone; do
        printf '  - path: %s\n    name: %s\n    area: test\n' "$P/$p" "$(basename "$p")"
    done
} > "$WORK/registry.yaml"

snapshot() { (cd "$P" && find . -type f -not -path '*/.git/*' -exec sha256sum {} + | sort); }

run() { OBSIDIAN_VAULT_PATH="$V" bash "$TOOL" --registry "$WORK/registry.yaml" "$@"; }

# --- --dry-run changes nothing --------------------------------------------------
before="$(snapshot)"
out="$(run --dry-run 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "--dry-run exit $rc: $out"
[ "$(snapshot)" = "$before" ] || fail "--dry-run changed a file"
echo "$out" | grep -q 'alpha' || fail "--dry-run does not list alpha: $out"
ok "--dry-run lists the work and changes no file"

# --- a real run ---------------------------------------------------------------
out="$(run 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "run exit $rc: $out"
for p in alpha beta; do
    grep -q '^# Vault context for' "$P/$p/.claude/vault-context.md" \
        || fail "$p sidecar not rewritten: $(cat "$P/$p/.claude/vault-context.md")"
done
ok "the two linked projects get rewritten sidecars"

[ -e "$P/gamma/.claude/vault-context.md" ] && fail "unlinked gamma got a sidecar"
[ -e "$P/area/.claude/vault-context.md" ] && fail "the area directory got a sidecar"
[ -e "$P/area/child/.claude/vault-context.md" ] && fail "unlinked area/child got a sidecar"
ok "an unlinked project gets no sidecar"

echo "$out" | grep -E "area directory.*$P/area\$|$P/area\$.*area directory|area directory: $P/area" >/dev/null \
    || fail "the area directory is not reported as skipped: $out"
ok "an area directory in the registry is skipped with a line saying so"

echo "$out" | grep -q "$P/gone" || fail "the missing folder is not reported: $out"
ok "a project whose folder is missing is reported and the run continues"

# --- a failing project makes the run exit 1, others still refresh -----------------
echo "stale again" > "$P/beta/.claude/vault-context.md"
chmod a-w "$P/alpha/.claude"
out="$(run 2>&1)"; rc=$?
chmod u+w "$P/alpha/.claude"
[ "$rc" -eq 1 ] || fail "a failed project should exit 1, got $rc: $out"
echo "$out" | grep -q "$P/alpha" || fail "the failed project is not named: $out"
grep -q '^# Vault context for' "$P/beta/.claude/vault-context.md" || fail "beta not refreshed after alpha failed"
ok "a failed project is named, the others still refresh, and the exit code is 1"

# --- usage ----------------------------------------------------------------------
out="$(bash "$TOOL" 2>&1)"; rc=$?
[ "$rc" -eq 2 ] || fail "no --registry exit $rc (want 2): $out"
ok "a missing --registry is a usage error (exit 2)"

echo "PASS: test_vault_context_refresh_all.sh"
