#!/usr/bin/env bash
# test_vault_context_area_dirs.sh — vault-context must not write a sidecar into
# an *area directory* (a grouping folder that merely holds project repos).
#
# Covers both halves of the guard, which share one rule
# (plugins/vault-context/scripts/lib/eligibility.sh):
#   write path  — write-context.sh refuses with exit 4 and creates nothing
#   detect path — validate-link.sh reports link-area-directory for a sidecar
#                 that predates the guard
#
# Every case runs against a fixture registry via VAULT_CONTEXT_REGISTRY, so the
# test says nothing about the machine it runs on.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WRITE="$ROOT/plugins/vault-context/scripts/write-context.sh"
VALIDATE="$ROOT/plugins/vault-context/scripts/validate-link.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$WRITE" ]    || fail "missing $WRITE"
[ -f "$VALIDATE" ] || fail "missing $VALIDATE"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- fixture tree ------------------------------------------------------------
# area/                     registered, holds registered children  → refuse
# area/child/               registered + git repo                  → accept
# area/plain-child/         registered, not a repo, no children    → accept
# stray/                    unregistered, not a repo               → refuse
# fresh/                    unregistered git repo                  → accept
AREA="$WORK/area"
mkdir -p "$AREA/child" "$AREA/plain-child" "$WORK/stray" "$WORK/fresh"
git -C "$AREA/child" init -q
git -C "$WORK/fresh" init -q

REGISTRY="$WORK/projects-registry.yaml"
cat > "$REGISTRY" <<YAML
version: 1
projects:
  - path: $AREA
    name: area
    enabled: true
  - path: $AREA/child
    name: child
    enabled: true
  - path: $AREA/plain-child
    name: plain-child
    enabled: true
YAML

export VAULT_CONTEXT_REGISTRY="$REGISTRY"

# write_sidecar <target-dir> — run the write path for that project root.
# Echoes the exit code; the sidecar path is <target-dir>/.claude/vault-context.md.
write_sidecar() {
    local target="$1" rc=0
    echo NO_MATCHES | bash "$WRITE" "$(basename "$target")" "$WORK/vault" \
        "$target/.claude/vault-context.md" >/dev/null 2>&1 || rc=$?
    echo "$rc"
}

# --- Test 1: registered area directory → refused, nothing written ------------
# The case this guard exists for. `area` is a registry entry *and* has
# registered projects beneath it, so registration alone must not admit it.
rc="$(write_sidecar "$AREA")"
[ "$rc" = "4" ] || fail "registered area dir: expected exit 4, got $rc"
[ ! -e "$AREA/.claude" ] || fail "registered area dir: left a .claude/ behind"
ok "registered dir holding registered projects → refused (exit 4), nothing written"

# The refusal has to say why, and name the registry it decided from.
msg="$(echo NO_MATCHES | bash "$WRITE" area "$WORK/vault" \
        "$AREA/.claude/vault-context.md" 2>&1 >/dev/null)"
case "$msg" in
    *"area directory — not a project"*) ;;
    *) fail "refusal message missing 'area directory — not a project': $msg" ;;
esac
case "$msg" in
    *"$REGISTRY"*) ;;
    *) fail "refusal message does not name the registry: $msg" ;;
esac
ok "refusal explains itself and names the registry"

# --- Test 2: unregistered, non-repo directory → refused ----------------------
rc="$(write_sidecar "$WORK/stray")"
[ "$rc" = "4" ] || fail "unregistered non-repo dir: expected exit 4, got $rc"
[ ! -e "$WORK/stray/.claude" ] || fail "unregistered non-repo dir: left a .claude/ behind"
ok "unregistered non-repo dir → refused (exit 4), nothing written"

# --- Test 3: registered project → accepted -----------------------------------
rc="$(write_sidecar "$AREA/child")"
[ "$rc" = "0" ] || fail "registered project: expected exit 0, got $rc"
[ -f "$AREA/child/.claude/vault-context.md" ] || fail "registered project: no sidecar written"
ok "registered project → accepted, sidecar written"

# A registered leaf that is not a repo is still a project — the containment
# clause must not refuse everything that happens to be registered.
rc="$(write_sidecar "$AREA/plain-child")"
[ "$rc" = "0" ] || fail "registered non-repo leaf: expected exit 0, got $rc"
[ -f "$AREA/plain-child/.claude/vault-context.md" ] || fail "registered non-repo leaf: no sidecar"
ok "registered leaf with no registered children → accepted"

# --- Test 4: unregistered git repo → accepted --------------------------------
rc="$(write_sidecar "$WORK/fresh")"
[ "$rc" = "0" ] || fail "unregistered git repo: expected exit 0, got $rc"
[ -f "$WORK/fresh/.claude/vault-context.md" ] || fail "unregistered git repo: no sidecar written"
ok "unregistered git repo → accepted, sidecar written"

# --- Test 5: a refusal does not kill the upstream pipe stage -----------------
# write-context.sh is the tail of `extract-project-signals.sh | match-index.py |
# write-context.sh` and is the only stage that can now exit before reading its
# stdin. If it does that without draining the pipe, match-index.py takes SIGPIPE
# and prints a BrokenPipeError traceback underneath the refusal message.
err="$WORK/refusal.err"
python3 -c 'import sys; sys.stdout.write("x" * 5000000)' 2>/dev/null \
    | bash "$WRITE" stray "$WORK/vault" "$WORK/stray/.claude/vault-context.md" >/dev/null 2>"$err"
grep -q 'BrokenPipeError' "$err" && fail "refusal killed the upstream pipe stage: $(cat "$err")"
grep -q 'area directory — not a project' "$err" || fail "refusal message missing from stderr: $(cat "$err")"
ok "refusal drains stdin — no BrokenPipeError from the upstream stage"

# --- Test 6: detect path reports a pre-existing area sidecar -----------------
# A sidecar written before the guard existed is not reachable through the write
# path any more, so validate-link.sh is the only thing that can surface it.
if command -v jq >/dev/null 2>&1; then
    mkdir -p "$AREA/.claude"
    cp "$AREA/child/.claude/vault-context.md" "$AREA/.claude/vault-context.md"

    out="$(bash "$VALIDATE" "$AREA" --json 2>/dev/null)"
    rule="$(printf '%s' "$out" | jq -r '.findings[] | select(.rule=="link-area-directory") | .severity')"
    [ "$rule" = "error" ] || fail "validate-link.sh did not report link-area-directory as an error: $out"
    [ "$(printf '%s' "$out" | jq -r '.verdict')" = "fail" ] || fail "expected verdict fail for an area sidecar"
    ok "pre-existing area sidecar → validate-link.sh reports link-area-directory (error)"

    out="$(bash "$VALIDATE" "$AREA/child" --json 2>/dev/null)"
    [ "$(printf '%s' "$out" | jq -r '[.findings[]|select(.rule=="link-area-directory")]|length')" = "0" ] \
        || fail "validate-link.sh wrongly flagged a real project as an area directory"
    ok "real project sidecar → no link-area-directory finding"
else
    echo "  skip: jq not installed — validate-link.sh cases not run"
fi

echo "ALL OK"
