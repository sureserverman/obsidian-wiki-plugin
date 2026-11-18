#!/usr/bin/env bash
# test_vault_context_stack_validator.sh — validate-stacks.sh turns the sync tool's
# --check --lint --json output into lane findings, and stays silent where no stack
# page exists.
#
# The vault comes from OBSIDIAN_VAULT_PATH, the stacks folder from
# VAULT_CONTEXT_STACKS_DIR and the Claude config folder from CLAUDE_CONFIG_DIR, all
# fixtures, so nothing here reads the real machine.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$ROOT/plugins/vault-context/scripts"
VAL="$SCRIPTS/validate-stacks.sh"
SYNC="$SCRIPTS/sync-stack-rules.py"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$VAL" ]  || fail "missing $VAL"
[ -f "$SYNC" ] || fail "missing $SYNC"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

V="$WORK/vault"; R="$WORK/stacks"; P="$WORK/project"
mkdir -p "$V" "$R" "$P/src" "$WORK/cfg"
touch "$V/index.md" "$P/src/main.rs"
export OBSIDIAN_VAULT_PATH="$V" VAULT_CONTEXT_STACKS_DIR="$R" CLAUDE_CONFIG_DIR="$WORK/cfg"

run_lane() { bash "$VAL" "$P" --json 2>/dev/null; }
has() { # <json> <rule> <severity>
    printf '%s' "$1" | jq -e --arg r "$2" --arg s "$3" \
        '[.findings[] | select(.rule==$r and .severity==$s)] | length > 0' >/dev/null
}

# --- no Portfolio/stacks folder: the lane adds nothing --------------------------
out="$(run_lane)"
printf '%s' "$out" | jq -e '.findings | length == 0' >/dev/null \
    || fail "findings with no stacks folder: $out"
printf '%s' "$out" | jq -e '.verdict == "pass"' >/dev/null || fail "verdict with no stacks folder: $out"
out="$(bash "$SCRIPTS/validate.sh" "$P" --json 2>/dev/null)"
printf '%s' "$out" | jq -e '[.findings[] | select(.rule|startswith("stack-"))] | length == 0' >/dev/null \
    || fail "orchestrator reports stack findings with no stacks folder: $out"
ok "with no Portfolio/stacks/ folder the lane adds no finding and the verdict is pass"

# --- fixture pages ---------------------------------------------------------------
ST="$V/Portfolio/stacks"; mkdir -p "$ST"
echo src > "$WORK/src.txt"
page() { # <slug> <frontmatter-extra> <body>
    printf -- '---\nstack: %s\n%s\nchecked: 2026-11-17\n---\n%s\n' "$1" "$2" "$3" > "$ST/$1.md"
}
page alpha "paths: [\"**/*.rs\"]
sources: [\"$WORK/src.txt\"]" "Alpha."
page beta  "paths: [\"**/*.kt\"]
sources: [\"$WORK/src.txt\"]" "Beta."
python3 "$SYNC" --vault "$V" --stacks-dir "$R" >/dev/null 2>&1 || fail "fixture sync"

out="$(run_lane)"
printf '%s' "$out" | jq -e '.verdict == "pass"' >/dev/null || fail "in-sync fixture not pass: $out"
ok "an in-sync fixture passes clean"

# edited page → stale; never-synced page → missing; missing source → source-missing
page alpha "paths: [\"**/*.rs\"]
sources: [\"$WORK/src.txt\"]" "Alpha, edited."
page gamma "paths: [\"**/*.go\"]
sources: [\"$WORK/src.txt\"]" "Gamma."
page beta  "paths: [\"**/*.kt\"]
sources: [\"$WORK/gone.txt\"]" "Beta."
python3 "$SYNC" --vault "$V" --stacks-dir "$R" --only beta >/dev/null 2>&1
# delta has no paths → invalid page
printf -- '---\nstack: delta\nsources: ["%s"]\nchecked: 2026-11-17\n---\nNo paths.\n' "$WORK/src.txt" > "$ST/delta.md"
# unmarked vault-stack file → foreign
printf -- '---\npaths: ["**/*.c"]\n---\nHand written.\n' > "$R/vault-stack-epsilon.md"

out="$(run_lane)"
has "$out" stack-rule-stale     warn  || fail "no stack-rule-stale warn: $out"
has "$out" stack-rule-missing   warn  || fail "no stack-rule-missing warn: $out"
has "$out" stack-source-missing warn  || fail "no stack-source-missing warn: $out"
has "$out" stack-page-invalid   error || fail "no stack-page-invalid error: $out"
has "$out" stack-rule-foreign   error || fail "no stack-rule-foreign error: $out"
printf '%s' "$out" | jq -e '.verdict == "fail"' >/dev/null || fail "verdict not fail: $out"
printf '%s' "$out" | jq -e '[.findings[] | select(.rule=="stack-rule-stale")][0].path | test("alpha")' >/dev/null \
    || fail "stale finding does not name alpha: $out"
printf '%s' "$out" | jq -e '[.findings[] | select(.rule=="stack-rule-missing")][0].path | test("gamma")' >/dev/null \
    || fail "missing finding does not name gamma: $out"
ok "stale, missing, source-missing (warn) and page-invalid, rule-foreign (error) are each reported"

# A rule whose page is gone is reported stale.
rm "$ST/gamma.md" "$ST/delta.md" "$R/vault-stack-epsilon.md"
python3 "$SYNC" --vault "$V" --stacks-dir "$R" >/dev/null 2>&1
rm "$ST/alpha.md"
out="$(run_lane)"
printf '%s' "$out" | jq -e '[.findings[] | select(.rule=="stack-rule-stale" and (.path|test("vault-stack-alpha")) and (.message|test("gone")))] | length == 1' >/dev/null \
    || fail "orphan rule not reported as stack-rule-stale: $out"
ok "a rule whose page is gone is reported as stack-rule-stale"
page alpha "paths: [\"**/*.rs\"]
sources: [\"$WORK/src.txt\"]" "Alpha."
printf -- '---\npaths: ["**/*.c"]\n---\nHand written.\n' > "$R/vault-stack-epsilon.md"

# The orchestrator picks the lane up.
out="$(bash "$SCRIPTS/validate.sh" "$P" --json 2>/dev/null)"
has "$out" stack-rule-foreign error || fail "validate.sh does not carry the stack lane: $out"
ok "validate.sh carries the stack lane's findings"

# The validator holds no rule of its own: it only maps the sync tool's JSON.
grep -q 'sync-stack-rules.py' "$VAL" || fail "validate-stacks.sh does not call sync-stack-rules.py"
grep -q -- '--check' "$VAL" && grep -q -- '--lint' "$VAL" && grep -q -- '--json' "$VAL" \
    || fail "validate-stacks.sh does not call --check --lint --json"
ok "validate-stacks.sh reads sync-stack-rules.py --check --lint --json"

echo "PASS: test_vault_context_stack_validator.sh"
