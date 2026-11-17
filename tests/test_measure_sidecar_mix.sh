#!/usr/bin/env bash
# test_measure_sidecar_mix.sh — scripts/measure-sidecar-mix.py reads the sidecars a
# registry reaches and prints the mix metrics, and --assert fails when a metric is
# beyond its bound.
#
# Fixture: three registered projects with hand-written sidecars, one registered
# project without a sidecar, a fixture vault with Projects/ pages and one stack page.
# Hand-computed expectations:
#   alpha  Plans 2 of 4 (0.5), has Technologies, Projects/alpha exists but unlisted
#   beta   Plans 1 of 4 (0.25), no Technologies/Platforms, no Projects/beta page
#   gamma  Plans 0 of 2 (0.0), Platforms + own Projects/gamma listed, tracks
#          src/main.rs so the rust stack applies, but its sidecar has no stack block
#   delta  no sidecar → not measured
# → projects 3, plans_share_median 0.25, no_tech_or_platform 1,
#   own_project_missing 1, stack_block_missing 1
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOL="$ROOT/scripts/measure-sidecar-mix.py"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$TOOL" ] || fail "missing $TOOL"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
V="$WORK/vault"; P="$WORK/projects"
mkdir -p "$V/Projects" "$V/Portfolio/stacks"
touch "$V/Projects/alpha.md" "$V/Projects/gamma.md"
printf '%s\n' "# Index" "" "## Projects/" "" "### [[alpha]]" "- path: Projects/alpha.md" "" \
    "### [[Gamma]]" "- path: Projects/gamma.md" > "$V/index.md"
printf -- '---\nstack: rust\npaths: ["**/*.rs"]\nsources: ["%s"]\nchecked: 2026-11-17\n---\nRust.\n' "$V" \
    > "$V/Portfolio/stacks/rust.md"

sidecar() { # <project> <body lines...>
    mkdir -p "$P/$1/.claude"
    {
        printf '# Vault context for %s\n\n<!-- vault-context:body:start -->\n\n' "$1"
        shift
        printf '%s\n' "$@"
        printf '\n<!-- vault-context:body:end -->\n\n---\n*footer*\n'
    } > "$P/$(basename "$P/$1")/.claude/vault-context.md"
}
for p in alpha beta gamma delta; do mkdir -p "$P/$p"; git -C "$P/$p" init -q; done
mkdir -p "$P/gamma/src"; echo 'fn main(){}' > "$P/gamma/src/main.rs"; git -C "$P/gamma" add -A

sidecar alpha "## Plans/" "" "- [[P1]] — \`x\` — s" "- [[P2]] — \`x\` — s" "" \
              "## Technologies/" "" "- [[Rust]] — \`x\` — s" "- [[Python]] — \`x\` — s"
sidecar beta  "## Gotchas/" "" "- [[G1]] — \`x\` — s" "- [[G2]] — \`x\` — s" "- [[G3]] — \`x\` — s" "" \
              "## Plans/" "" "- [[P3]] — \`x\` — s"
sidecar gamma "## Platforms/" "" "- [[Linux]] — \`x\` — s" "" "## Projects/" "" "- [[Gamma]] — \`x\` — s"

{
    echo "version: 1"; echo "projects:"
    for p in alpha beta gamma delta; do
        printf '  - path: %s\n    name: %s\n    area: test\n    enabled: true\n' "$P/$p" "$p"
    done
} > "$WORK/registry.yaml"

run() { python3 "$TOOL" --registry "$WORK/registry.yaml" --vault "$V" "$@"; }

out="$(run)"; rc=$?
[ "$rc" -eq 0 ] || fail "plain run exit $rc: $out"
printf '%s' "$out" | python3 -c '
import json, sys
d = json.load(sys.stdin)
want = {"projects": 3, "plans_share_median": 0.25, "no_tech_or_platform": 1,
        "own_project_missing": 1, "stack_block_missing": 1}
bad = {k: (d.get(k), v) for k, v in want.items() if d.get(k) != v}
sys.exit("mismatch (got, want): %r" % bad if bad else 0)
' || fail "metrics differ from the hand-computed values: $out"
ok "prints the hand-computed plans_share_median, no_tech_or_platform, own_project_missing, stack_block_missing"

run --assert plans-median-max=0.25 --assert no-tech-max=1 \
    --assert own-project-missing-max=1 --assert stack-block-missing-max=1 >/dev/null \
    || fail "assertions at the printed values failed"
ok "assertions at the printed values pass"

for a in plans-median-max=0.24 no-tech-max=0 own-project-missing-max=0 stack-block-missing-max=0; do
    err="$(run --assert "$a" 2>&1 >/dev/null)"; rc=$?
    [ "$rc" -eq 1 ] || fail "--assert $a beyond the printed value exit $rc (want 1)"
    echo "$err" | grep -q "${a%%=*}" || fail "--assert $a failure does not name the assertion: $err"
done
ok "an --assert beyond a printed value exits 1 and names it"

err="$(run --assert bogus=1 2>&1 >/dev/null)"; rc=$?
[ "$rc" -eq 2 ] || fail "unknown --assert key exit $rc (want 2): $err"
ok "an unknown --assert key is a usage error (exit 2)"

echo "PASS: test_measure_sidecar_mix.sh"
