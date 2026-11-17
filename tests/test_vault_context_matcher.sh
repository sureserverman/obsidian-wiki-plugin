#!/usr/bin/env bash
# test_vault_context_matcher.sh — match-index.py picks a balanced page set.
#
# Fixture index (tests/fixtures/vault-context-matcher/index.md):
#   40 Plans/ pages tagged `plan, stage`      — common tokens, many pages
#   12 Gotchas/ pages tagged `gotcha, pitfall`
#   Technologies/Zephyrine tagged `zephyrine, plan` — `zephyrine` is on no other page
#   Projects/alpha, Portfolio Integrations "alpha integration" — match no signal
#
# Checks: rare tokens outweigh common ones (ln(N/df)), Plans/ capped at 5,
# every other category at most 8, the own Projects/ page and the own
# Portfolio Integrations page are kept, and under 5 scoring pages → NO_MATCHES.
#
# The registry is a fixture under a throwaway HOME, so the test says nothing
# about the machine it runs on.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MATCH="$ROOT/plugins/vault-context/scripts/match-index.py"
INDEX="$ROOT/tests/fixtures/vault-context-matcher/index.md"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$MATCH" ] || fail "missing $MATCH"
[ -f "$INDEX" ] || fail "missing $INDEX"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/home/.claude" "$WORK/alpha" "$WORK/beta" "$WORK/gamma" "$WORK/checkout"
# `checkout` is registered as alpha; the alpha/beta folders are not registered,
# so they fall back to their folder name.
cat > "$WORK/home/.claude/projects-registry.yaml" <<YAML
version: 1
projects:
  - path: $WORK/checkout
    name: alpha
    enabled: true
YAML

SIGNALS="plan
stage
gotcha
zephyrine"

# run_in <dir> <signals> — run the matcher from <dir>; prints its stdout.
run_in() {
    ( cd "$1" && printf '%s\n' "$2" | HOME="$WORK/home" python3 "$MATCH" "$INDEX" )
}

# count <json> <category> — number of pages listed under <category>.
count() {
    printf '%s' "$1" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(len(d["matches_by_category"].get(sys.argv[1], [])))' "$2"
}

# has <json> <title> — exit 0 when a page with <title> is in the output.
has() {
    printf '%s' "$1" | python3 -c '
import json, sys
d = json.load(sys.stdin)
titles = {p["title"] for ps in d["matches_by_category"].values() for p in ps}
sys.exit(0 if sys.argv[1] in titles else 1)' "$2"
}

# --- Test 1: Plans/ capped at 5 ----------------------------------------------
out="$(run_in "$WORK/alpha" "$SIGNALS")" || fail "matcher exited non-zero"
[ "$out" != "NO_MATCHES" ] || fail "fixture with 53 scoring pages printed NO_MATCHES"
n="$(count "$out" "Plans/")"
[ "$n" = "5" ] || fail "expected exactly 5 Plans/ pages, got $n"
ok "Plans/ capped at 5"

# --- Test 2: every other category at most 8 ----------------------------------
over="$(printf '%s' "$out" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(" ".join(f"{c}={len(ps)}" for c, ps in d["matches_by_category"].items()
               if c != "Plans/" and len(ps) > 8))')"
[ -z "$over" ] || fail "category over the cap of 8: $over"
n="$(count "$out" "Gotchas/")"
[ "$n" = "8" ] || fail "expected Gotchas/ filled to its cap of 8, got $n"
ok "other categories at most 8 (Gotchas/ = 8)"

# --- Test 3: the rare-token page outranks every Plans page -------------------
printf '%s' "$out" | python3 -c '
import json, sys
d = json.load(sys.stdin)["matches_by_category"]
tech = [p["score"] for p in d.get("Technologies/", []) if p["title"] == "Zephyrine"]
if not tech:
    sys.exit("Technologies/Zephyrine missing")
worst = max(p["score"] for p in d.get("Plans/", []))
if not tech[0] > worst:
    sys.exit(f"Zephyrine {tech[0]} does not outrank the best Plans page {worst}")
' || fail "rare token not weighted above common tokens"
ok "Technologies/Zephyrine outranks every Plans page"

# --- Test 4: own Projects/ page by folder name -------------------------------
has "$out" "alpha" || fail "Projects/alpha missing when cwd is named alpha"
ok "cwd named alpha → Projects/alpha kept although it scores 0"

out_beta="$(run_in "$WORK/beta" "$SIGNALS")" || fail "matcher exited non-zero in beta"
has "$out_beta" "alpha" && fail "Projects/alpha present when cwd is named beta"
ok "cwd named beta → Projects/alpha absent"

out_gamma="$(run_in "$WORK/gamma" "$SIGNALS")" || fail "matcher exited non-zero in gamma"
has "$out_gamma" "Gamma Tool" || fail "Projects/gamma.md (titled Gamma Tool) missing when cwd is named gamma"
ok "cwd named gamma → Projects/gamma.md kept by its file name although its title differs"

# --- Test 5: registry slug and the own Portfolio Integrations page -----------
out_reg="$(run_in "$WORK/checkout" "$SIGNALS")" || fail "matcher exited non-zero in checkout"
has "$out_reg" "alpha" || fail "registry maps cwd to alpha but Projects/alpha is missing"
has "$out_reg" "alpha integration" || fail "own Portfolio Integrations page not guaranteed"
n="$(count "$out_reg" "Plans/")"
[ "$n" = "5" ] || fail "guarantees broke the Plans/ cap: $n"
ok "registered cwd → own Projects/ and Portfolio Integrations pages kept"

has "$out" "alpha integration" && fail "integration page guaranteed for an unregistered cwd"
ok "unregistered cwd → no integration guarantee"

# --- Test 6: fewer than 5 scoring pages → NO_MATCHES -------------------------
out_few="$(run_in "$WORK/alpha" "zephyrine")" || fail "matcher exited non-zero on one signal"
[ "$out_few" = "NO_MATCHES" ] || fail "1 scoring page did not print NO_MATCHES: $out_few"
out_none="$(run_in "$WORK/alpha" "nothing-matches-this")" || fail "matcher exited non-zero on no match"
[ "$out_none" = "NO_MATCHES" ] || fail "0 scoring pages did not print NO_MATCHES"
ok "under 5 scoring pages → NO_MATCHES"

echo "ALL OK"
