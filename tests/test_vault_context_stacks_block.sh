#!/usr/bin/env bash
# test_vault_context_stacks_block.sh — write-context.sh renders the `## Stack rules`
# block (via render-stacks.py) into the sidecar for the stacks whose `paths:` match
# a project file, and leaves it out entirely when none applies.
#
# Covers:
#   - a Rust project gets a block naming `alpha`, its glob, its page path and its
#     related link, and not `beta` (whose glob matches nothing there)
#   - a project matching no stack has neither marker — no empty block
#   - a vault with no Portfolio/stacks folder renders no block
#   - an existing PORTFOLIO-STATUS block survives the rewrite byte for byte
#   - a stack page that fails to parse is skipped with a warning on stderr, and the
#     sidecar is still written
#   - both the NO_MATCHES and the JSON branch carry the block
#
# Every case runs against a fixture vault and an empty fixture registry via
# VAULT_CONTEXT_REGISTRY, so the test says nothing about the machine it runs on.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WRITE="$ROOT/plugins/vault-context/scripts/write-context.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$WRITE" ]  || fail "missing $WRITE"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
WORK="$(cd "$WORK" && pwd -P)"

START='<!-- vault-context:stacks:start -->'
END='<!-- vault-context:stacks:end -->'
FIRST_LINE='These load on their own when a matching file is read or edited. Open a page to read it sooner.'

# --- fixture vault -----------------------------------------------------------
VAULT="$WORK/vault"
STACKS="$VAULT/Portfolio/stacks"
mkdir -p "$STACKS"
cat > "$STACKS/alpha.md" <<EOF
---
stack: alpha
paths: ["**/*.rs"]
sources: [$WORK/sources/alpha.txt]
related: [Alpha Notes]
checked: 2026-01-01
---
Alpha rules body.
EOF
cat > "$STACKS/beta.md" <<EOF
---
stack: beta
paths: ["**/*.kt"]
sources: [$WORK/sources/beta.txt]
checked: 2026-01-01
---
Beta rules body.
EOF

EMPTY_VAULT="$WORK/empty-vault"
mkdir -p "$EMPTY_VAULT"

REGISTRY="$WORK/projects-registry.yaml"
: > "$REGISTRY"
export VAULT_CONTEXT_REGISTRY="$REGISTRY"

# --- fixture projects --------------------------------------------------------
# make_project <dir> <file> — a git repo with <file> staged (git ls-files sees it).
make_project() {
    mkdir -p "$1/$(dirname "$2")"
    printf 'x\n' > "$1/$2"
    git -C "$1" init -q
    git -C "$1" add "$2"
}
RUST="$WORK/alice-rust"
PLAIN="$WORK/alice-plain"
make_project "$RUST" src/main.rs
make_project "$PLAIN" README.txt

# run_write <project-dir> <vault> <stdin> — run write-context; stderr to $WORK/err.
# Echoes the exit code.
run_write() {
    local rc=0
    printf '%s\n' "$3" | bash "$WRITE" "$(basename "$1")" "$2" \
        "$1/.claude/vault-context.md" >/dev/null 2>"$WORK/err" || rc=$?
    echo "$rc"
}

# block_of <file> — the text between the stack markers (exclusive).
block_of() {
    awk -v s="$START" -v e="$END" '$0==e{f=0} f{print} $0==s{f=1}' "$1"
}

# --- Test 1: matching project gets the alpha block, not beta (NO_MATCHES) -----
rc="$(run_write "$RUST" "$VAULT" NO_MATCHES)"
[ "$rc" = "0" ] || fail "rust project: write-context exit $rc: $(cat "$WORK/err")"
SIDE="$RUST/.claude/vault-context.md"
grep -qxF "$START" "$SIDE" || fail "rust project: no start marker in sidecar"
grep -qxF "$END" "$SIDE"   || fail "rust project: no end marker in sidecar"
block="$(block_of "$SIDE")"
printf '%s\n' "$block" | grep -qxF '## Stack rules' || fail "block lacks '## Stack rules' heading"
printf '%s\n' "$block" | grep -qxF "$FIRST_LINE"   || fail "block lacks the first line"
printf '%s\n' "$block" | grep -qF 'alpha'           || fail "block does not name alpha"
printf '%s\n' "$block" | grep -qF '**/*.rs'         || fail "block does not name alpha's glob"
printf '%s\n' "$block" | grep -qF "$STACKS/alpha.md" || fail "block does not name alpha's page path"
printf '%s\n' "$block" | grep -qF '[[Alpha Notes]]' || fail "block does not link [[Alpha Notes]]"
printf '%s\n' "$block" | grep -q 'beta'             && fail "block names beta, whose glob matches nothing"
# Placement: after the body end marker, before the footer rule.
order="$(grep -nxF -e '<!-- vault-context:body:end -->' -e "$START" -e "$END" -e '---' "$SIDE" \
    | cut -d: -f2- | tr '\n' '|')"
[ "$order" = "<!-- vault-context:body:end -->|$START|$END|---|" ] \
    || fail "block out of place; marker order was: $order"
ok "rust project (NO_MATCHES) → block names alpha, its glob, page and [[Alpha Notes]]; not beta"

# --- Test 2: JSON branch carries the block too -------------------------------
rc="$(run_write "$RUST" "$VAULT" '{"index_date":"2026-01-01","matches_by_category":{}}')"
[ "$rc" = "0" ] || fail "rust project (JSON): write-context exit $rc: $(cat "$WORK/err")"
block_of "$SIDE" | grep -qF "$STACKS/alpha.md" || fail "JSON branch: block missing alpha"
ok "rust project (JSON) → block rendered"

# --- Test 3: project matching no stack → neither marker ----------------------
rc="$(run_write "$PLAIN" "$VAULT" NO_MATCHES)"
[ "$rc" = "0" ] || fail "plain project: write-context exit $rc: $(cat "$WORK/err")"
PSIDE="$PLAIN/.claude/vault-context.md"
[ -f "$PSIDE" ] || fail "plain project: no sidecar written"
grep -qF 'vault-context:stacks:start' "$PSIDE" && fail "plain project: start marker written (empty block)"
grep -qF 'vault-context:stacks:end' "$PSIDE"   && fail "plain project: end marker written (empty block)"
grep -qF '## Stack rules' "$PSIDE"             && fail "plain project: stack heading written"
grep -qF '<STACKS_BLOCK>' "$PSIDE"             && fail "plain project: placeholder left in sidecar"
# No blank lines piling up where the block would have been.
awk 'prev=="" && $0=="" {bad=1} {prev=$0} END{exit bad}' "$PSIDE" \
    || fail "plain project: consecutive blank lines left where the block was removed"
ok "project matching no stack → no markers, no placeholder, no stray blank lines"

# --- Test 4: vault without Portfolio/stacks → no block -----------------------
rc="$(run_write "$RUST" "$EMPTY_VAULT" NO_MATCHES)"
[ "$rc" = "0" ] || fail "empty vault: write-context exit $rc: $(cat "$WORK/err")"
grep -qF 'vault-context:stacks:start' "$SIDE" && fail "empty vault: block written"
ok "vault with no stacks folder → no block"

# --- Test 5: PORTFOLIO-STATUS block survives byte for byte -------------------
PS_BLOCK="$(printf '%s\n' \
    '<!-- PORTFOLIO-STATUS-BEGIN (managed by /vault-portfolio:portfolio rebuild) -->' \
    '## Portfolio status' \
    '' \
    '- **Home:** `Portfolio/alice-rust`  & more' \
    '<!-- PORTFOLIO-STATUS-END -->')"
rc="$(run_write "$RUST" "$VAULT" NO_MATCHES)"
[ "$rc" = "0" ] || fail "portfolio seed: write-context exit $rc"
printf '\n%s\n' "$PS_BLOCK" >> "$SIDE"
rc="$(run_write "$RUST" "$VAULT" NO_MATCHES)"
[ "$rc" = "0" ] || fail "portfolio rewrite: write-context exit $rc: $(cat "$WORK/err")"
got="$(awk '/<!-- PORTFOLIO-STATUS-BEGIN/{f=1} f{print} /PORTFOLIO-STATUS-END -->/{f=0}' "$SIDE")"
[ "$got" = "$PS_BLOCK" ] || fail "PORTFOLIO-STATUS block changed across the rewrite"
block_of "$SIDE" | grep -qF "$STACKS/alpha.md" || fail "portfolio rewrite: stack block lost"
ok "PORTFOLIO-STATUS block survives the rewrite byte for byte, beside the stack block"

# --- Test 6: a page that fails to parse is skipped with a warning ------------
cat > "$STACKS/gamma.md" <<EOF
---
stack: gamma
paths: ["**/*.rs"]
sources: [$WORK/sources/gamma.txt]
---
Missing its checked date.
EOF
rm -f "$SIDE"
rc="$(run_write "$RUST" "$VAULT" NO_MATCHES)"
[ "$rc" = "0" ] || fail "bad page: write-context exit $rc: $(cat "$WORK/err")"
[ -f "$SIDE" ] || fail "bad page: sidecar not written"
grep -qF 'gamma.md' "$WORK/err" || fail "bad page: no stderr warning naming gamma.md (stderr: $(cat "$WORK/err"))"
grep -qF 'checked' "$WORK/err"  || fail "bad page: warning does not give the reason"
block="$(block_of "$SIDE")"
printf '%s\n' "$block" | grep -qF "$STACKS/alpha.md" || fail "bad page: alpha dropped from the block"
printf '%s\n' "$block" | grep -q 'gamma' && fail "bad page: gamma listed despite failing to parse"
ok "unparseable page → warning on stderr, skipped, sidecar still written with alpha"

echo "PASS: test_vault_context_stacks_block.sh"
