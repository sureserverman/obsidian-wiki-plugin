#!/usr/bin/env bash
# test_vault_context_sync_hosts.sh — sync-stack-rules.py serves three hosts: Claude
# Code's stacks folder (the default, unchanged), a Cursor rule in each project where a
# stack applies, and a Codex home holding copies plus one pointer block. The lane
# (validate-stacks.sh) reports drift for each host in use.
#
# Every case runs against a fixture registry, vault, stacks folder, Claude config,
# Codex home and git config, so the test never reads or writes the machine's own.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$ROOT/plugins/vault-context/scripts"
SYNC="$SCRIPTS/sync-stack-rules.py"
VAL="$SCRIPTS/validate-stacks.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$SYNC" ] || fail "missing $SYNC"
command -v jq >/dev/null || fail "jq is required"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- isolation -----------------------------------------------------------------
export HOME="$WORK/home"; mkdir -p "$HOME"
: > "$WORK/gitconfig"
export GIT_CONFIG_GLOBAL="$WORK/gitconfig" GIT_CONFIG_NOSYSTEM=1 XDG_CONFIG_HOME="$WORK/xdg"
export CLAUDE_CONFIG_DIR="$WORK/cfg"; mkdir -p "$CLAUDE_CONFIG_DIR"
unset VAULT_CONTEXT_STACKS_DIR CODEX_HOME OBSIDIAN_VAULT_PATH

V="$WORK/vault"; ST="$V/Portfolio/stacks"; R="$WORK/stacks"; C="$WORK/codex"
AREA="$WORK/area"; P1="$AREA/rusty"; P2="$AREA/kotlin"; P3="$AREA/plain"
MISSING="$WORK/gone"
mkdir -p "$ST" "$R" "$C"

page() { # <slug> <paths-inline-list> <body>
    printf -- '---\nstack: %s\npaths: %s\nsources: ["%s"]\nchecked: 2026-11-20\n---\n%s' \
        "$1" "$2" "$ST" "$3" > "$ST/$1.md"
}
page alpha '["**/*.rs"]' $'# Alpha\n\nUse the alpha way.\n'
page beta  '["**/*.kt"]' $'# Beta\n\nBeta facts.\n'

repo() { # <dir> <file>...
    local d="$1"; shift
    mkdir -p "$d"; git init -q --template= "$d"
    printf '.cursor/\n' > "$d/.gitignore"
    for f in "$@"; do mkdir -p "$d/$(dirname "$f")"; echo x > "$d/$f"; done
    git -C "$d" add -A
}
repo "$P1" src/main.rs
repo "$P2" app/Main.kt
repo "$P3" README.txt

REG="$WORK/registry.yaml"
{
    echo "version: 1"; echo "projects:"
    for p in "$AREA" "$P1" "$P2" "$P3" "$MISSING"; do echo "  - path: $p"; done
} > "$REG"
export VAULT_CONTEXT_REGISTRY="$REG"

sync() { python3 "$SYNC" --vault "$V" --stacks-dir "$R" --codex-home "$C" "$@"; }

# --- 1. --host all --all-projects writes all three kinds --------------------------
out="$(sync --host all --all-projects 2>&1)"; rc=$?
[ "$rc" = 0 ] || fail "--host all --all-projects exited $rc: $out"
[ -f "$R/vault-stack-alpha.md" ] && [ -f "$R/vault-stack-beta.md" ] \
    || fail "Claude copies not written: $(ls "$R")"
[ -f "$P1/.cursor/rules/vault-stack-alpha.mdc" ] || fail "no Cursor rule for alpha in $P1"
[ ! -e "$P1/.cursor/rules/vault-stack-beta.mdc" ] || fail "beta rule written where beta does not apply"
[ -f "$P2/.cursor/rules/vault-stack-beta.mdc" ] || fail "no Cursor rule for beta in $P2"
[ ! -e "$P3/.cursor" ] || fail "a rule folder was made in a project where no stack applies"
[ ! -e "$AREA/.cursor" ] || fail "the area directory got a rule folder"
[ -f "$C/vault-stacks/alpha.md" ] && [ -f "$C/vault-stacks/beta.md" ] || fail "Codex copies not written"
grep -q 'vault-context:stacks:start' "$C/AGENTS.md" || fail "Codex AGENTS.md has no block"
printf '%s\n' "$out" | grep -q "$MISSING" || fail "the missing folder is not named: $out"
printf '%s\n' "$out" | grep -q "$AREA" || fail "the area directory is not named: $out"
ok "--host all --all-projects writes the Claude copies, the Cursor rules where a stack applies, and the Codex copies and block; it names what it skipped"

out="$(sync --check --host all --all-projects 2>&1)"; rc=$?
[ "$rc" = 0 ] || fail "--check right after a sync exited $rc: $out"
ok "--check --host all --all-projects exits 0 after a sync"

# --- 2. usage --------------------------------------------------------------------
for h in cursor all; do
    sync --host "$h" >/dev/null 2>&1; rc=$?
    [ "$rc" = 2 ] || fail "--host $h without --project or --all-projects exited $rc, not 2"
done
sync --host cursor --project "$P1" --all-projects >/dev/null 2>&1; rc=$?
[ "$rc" = 2 ] || fail "--project with --all-projects exited $rc, not 2"
for h in cursor codex all; do
    sync --host "$h" --all-projects --only alpha >/dev/null 2>&1; rc=$?
    [ "$rc" = 2 ] || fail "--only with --host $h exited $rc, not 2"
done
sync --host nope >/dev/null 2>&1; rc=$?
[ "$rc" = 2 ] || fail "--host nope exited $rc, not 2"
ok "usage errors exit 2: cursor/all without projects, --project with --all-projects, --only beyond claude, an unknown host"

# --- 3. the lane, before any drift -------------------------------------------------
export OBSIDIAN_VAULT_PATH="$V" VAULT_CONTEXT_STACKS_DIR="$R" CODEX_HOME="$C"
lane="$(bash "$VAL" "$P1" --json)" || fail "validate-stacks.sh failed on a synced project: $lane"
printf '%s' "$lane" | jq -e '[.findings[]? | select(.rule | test("^stack-(cursor|codex)"))] | length == 0' >/dev/null \
    || fail "lane reports Cursor/Codex drift on a synced project: $lane"
ok "the lane is clean for a synced project"

# --- 4. one page edit is drift under every host -----------------------------------
page alpha '["**/*.rs", "**/build.rs"]' $'# Alpha\n\nUse the alpha way, edited.\n'
out="$(sync --check --host all --all-projects 2>&1)"; rc=$?
[ "$rc" = 1 ] || fail "--check after a page edit exited $rc, not 1: $out"
for h in claude cursor codex; do
    printf '%s\n' "$out" | grep -E "^$h: .*alpha" >/dev/null || fail "--check does not name alpha under $h: $out"
done
printf '%s\n' "$out" | grep -E "^(claude|cursor|codex): .*beta" >/dev/null && fail "--check names beta, which did not change: $out"
ok "after one page edit, --check exits 1 and names that slug under claude, cursor and codex only"

lane="$(bash "$VAL" "$P1" --json)"
for r in stack-cursor-rule-stale stack-codex-copy-stale stack-codex-block-stale; do
    printf '%s' "$lane" | jq -e --arg r "$r" '[.findings[]? | select(.rule == $r and .severity == "warn")] | length >= 1' >/dev/null \
        || fail "lane does not report $r as a warning: $lane"
done
ok "the lane reports stack-cursor-rule-stale, stack-codex-copy-stale and stack-codex-block-stale as warnings"

# A host the owner does not use is not reported: no Codex copies folder, no Cursor rule.
lane="$(CODEX_HOME="$WORK/no-codex" bash "$VAL" "$P3" --json)"
printf '%s' "$lane" | jq -e '[.findings[]? | select(.rule | test("^stack-(cursor|codex)"))] | length == 0' >/dev/null \
    || fail "lane reports a host that is not in use: $lane"
ok "the lane stays quiet about a host not in use"

sync --host all --all-projects >/dev/null 2>&1 || fail "re-sync after the edit failed"
grep -q 'build.rs' "$P1/.cursor/rules/vault-stack-alpha.mdc" || fail "Cursor rule not updated"
grep -q 'build.rs' "$C/AGENTS.md" || fail "Codex block not updated"
sync --check --host all --all-projects >/dev/null 2>&1 || fail "--check not clean after the re-sync"
ok "a re-sync brings every host back in step"

# --- 5. a project that would commit its rule is refused; the others continue -------
P4="$AREA/tracked"; repo "$P4" lib/x.rs
rm "$P4/.gitignore"; git -C "$P4" rm -q --cached .gitignore 2>/dev/null
echo "  - path: $P4" >> "$REG"
before_p1="$(sha256sum "$P1/.cursor/rules/vault-stack-alpha.mdc")"
page alpha '["**/*.rs", "**/build.rs"]' $'# Alpha\n\nUse the alpha way, edited twice.\n'
out="$(sync --host cursor --all-projects 2>&1)"; rc=$?
[ "$rc" = 1 ] || fail "a refused project did not make the run exit 1 (got $rc): $out"
printf '%s\n' "$out" | grep -q 'would be committed' || fail "refusal does not say 'would be committed': $out"
[ ! -e "$P4/.cursor" ] || fail "a rule was written where git would commit it"
[ "$(sha256sum "$P1/.cursor/rules/vault-stack-alpha.mdc")" != "$before_p1" ] \
    || fail "the other projects were not synced after one was refused"
ok "a project whose git would commit .cursor/ is refused, gets nothing, and the other projects are still synced"
sed -i "\#$P4#d" "$REG"
sync --host all --all-projects >/dev/null 2>&1 || fail "re-sync failed"

# --- 6. a vault showing no pages removes nothing, on any host ----------------------
mv "$ST" "$WORK/stacks-away"; mkdir -p "$ST"
snap() { find "$R" "$C" "$P1/.cursor" "$P2/.cursor" -type f -exec sha256sum {} + | sort; }
before="$(snap)"
out="$(sync --host all --all-projects 2>&1)"; rc=$?
[ "$rc" = 2 ] || fail "an empty vault exited $rc, not 2: $out"
[ "$(snap)" = "$before" ] || fail "an empty vault removed or changed generated files"
out="$(sync --host codex 2>&1)"; rc=$?
[ "$rc" = 2 ] || fail "an empty vault with --host codex exited $rc, not 2: $out"
out="$(sync --host cursor --project "$P1" 2>&1)"; rc=$?
[ "$rc" = 2 ] || fail "an empty vault with --host cursor exited $rc, not 2: $out"
[ "$(snap)" = "$before" ] || fail "an empty vault removed or changed generated files"
ok "a vault showing no stack pages removes nothing on any host and exits 2"
rmdir "$ST"; mv "$WORK/stacks-away" "$ST"

# --- 7. a broken Codex block is refused; the file is untouched ---------------------
printf 'owner text\n<!-- vault-context:stacks:start -->\n' > "$C/AGENTS.md"
sum="$(sha256sum "$C/AGENTS.md")"
out="$(sync --host codex 2>&1)"; rc=$?
[ "$rc" = 1 ] || fail "a start marker with no end exited $rc, not 1: $out"
[ "$(sha256sum "$C/AGENTS.md")" = "$sum" ] || fail "a refused AGENTS.md was changed"
ok "a Codex AGENTS file with a start marker and no end is refused and left unchanged"

# --- 8. Stage 1 review cases ------------------------------------------------------
# Restore a clean Codex home and a clean sync.
rm -rf "$C"; mkdir -p "$C"
sync --host all --all-projects >/dev/null 2>&1 || fail "clean re-sync failed"

# Per-file lines: a write names each rule and copy it changed.
page beta '["**/*.kt"]' $'# Beta\n\nBeta facts, edited.\n'
out="$(sync --host all --all-projects 2>&1)" || fail "sync after a beta edit failed: $out"
printf '%s\n' "$out" | grep -qx "cursor: updated $P2/.cursor/rules/vault-stack-beta.mdc" \
    || fail "no per-file cursor line for the updated rule: $out"
printf '%s\n' "$out" | grep -qx "codex: updated $C/vault-stacks/beta.md" \
    || fail "no per-file codex line for the updated copy: $out"
ok "a write prints one cursor:/codex: line per rule or copy it changed"

# Two registered folders in one repo, in both orders: one skip line or one
# same-folder line each, never silence, and the repo gets its rule once.
MONO="$WORK/mono"; repo "$MONO" sub/lib.rs; SUB="$MONO/sub"
for order in "$MONO $SUB" "$SUB $MONO"; do
    rm -rf "$MONO/.cursor"
    { echo "version: 1"; echo "projects:"; for p in $order; do echo "  - path: $p"; done; } > "$WORK/reg2.yaml"
    out="$(VAULT_CONTEXT_REGISTRY="$WORK/reg2.yaml" sync --host cursor --all-projects 2>&1)"; rc=$?
    [ "$rc" = 0 ] || fail "nested registry ($order) exited $rc: $out"
    [ -f "$MONO/.cursor/rules/vault-stack-alpha.mdc" ] || fail "nested registry ($order): no rule at the top level: $out"
    [ ! -e "$SUB/.cursor" ] || fail "nested registry ($order): a rule folder under the registered subfolder"
    for p in $order; do
        printf '%s\n' "$out" | grep -F "$p" >/dev/null || fail "nested registry ($order): $p is dropped with no line: $out"
    done
done
ok "a repo and a registered folder inside it, in either order, each get a line and the repo gets its rule once"

# A refused page: Claude and Cursor sync the rest; Codex is neither changed nor compared.
snapc() { find "$C" -type f -exec sha256sum {} + | sort; }
before="$(snapc)"
printf -- '---\nstack: gamma\npaths: ["**/*.go"]\nbogus: 1\nsources: ["%s"]\nchecked: 2026-11-20\n---\n# G\n' "$ST" > "$ST/gamma.md"
page alpha '["**/*.rs", "**/build.rs"]' $'# Alpha\n\nAlpha with a refused sibling.\n'
out="$(sync --host all --all-projects 2>&1)"; rc=$?
[ "$rc" = 1 ] || fail "a refused page did not exit 1: $out"
printf '%s\n' "$out" | grep -q 'codex: a stack page was refused, so the Codex home was not changed' \
    || fail "no codex line for the refused page: $out"
[ "$(snapc)" = "$before" ] || fail "the Codex home changed while a page was refused"
grep -q 'Alpha with a refused sibling' "$P1/.cursor/rules/vault-stack-alpha.mdc" || fail "Cursor did not sync the other pages"
grep -q 'Alpha with a refused sibling' "$R/vault-stack-alpha.md" || fail "Claude did not sync the other pages"
out="$(sync --check --host codex 2>&1)"
printf '%s\n' "$out" | grep -q 'orphan' && fail "check calls a refused page's copy an orphan: $out"
printf '%s\n' "$out" | grep -q 'not compared' || fail "check does not say Codex was not compared: $out"
lane="$(bash "$VAL" "$P1" --json)"
printf '%s' "$lane" | jq -e '[.findings[]? | select(.rule | test("^stack-codex"))] | length == 0' >/dev/null \
    || fail "the lane reports Codex findings the sync cannot clear while a page is refused: $lane"
printf '%s' "$lane" | jq -e '[.findings[]? | select(.rule == "stack-page-invalid")] | length == 1' >/dev/null \
    || fail "the lane does not report the refused page: $lane"
rm "$ST/gamma.md"
sync --host all --all-projects >/dev/null 2>&1 || fail "sync once the page is gone failed"
grep -q 'Alpha with a refused sibling' "$C/vault-stacks/alpha.md" || fail "Codex not synced once the page was fixed"
ok "a refused page: Claude and Cursor sync the rest, Codex is left and not compared, the lane names only the page"

# The lane's refusal codes.
printf 'owner\n<!-- vault-context:stacks:start -->\n' > "$C/AGENTS.md"
lane="$(bash "$VAL" "$P1" --json)"
printf '%s' "$lane" | jq -e '[.findings[]? | select(.rule == "stack-codex-refused" and .severity == "error")] | length >= 1' >/dev/null \
    || fail "the lane does not report stack-codex-refused: $lane"
rm "$C/AGENTS.md"; sync --host codex >/dev/null 2>&1 || fail "codex re-sync failed"
printf 'mine\n' > "$P1/.cursor/rules/vault-stack-zeta.mdc"
lane="$(bash "$VAL" "$P1" --json)"
printf '%s' "$lane" | jq -e '[.findings[]? | select(.rule == "stack-rule-foreign" and (.file // .path // "" | tostring | test("zeta")))] | length >= 1' >/dev/null \
    || printf '%s' "$lane" | grep -q 'vault-stack-zeta.mdc' || fail "the lane does not report a foreign Cursor rule: $lane"
rm "$P1/.cursor/rules/vault-stack-zeta.mdc"
rm "$P1/.gitignore"; git -C "$P1" rm -q --cached .gitignore 2>/dev/null
lane="$(bash "$VAL" "$P1" --json)"
printf '%s' "$lane" | jq -e '[.findings[]? | select(.rule == "stack-cursor-refused" and .severity == "warn")] | length >= 1' >/dev/null \
    || fail "the lane does not report stack-cursor-refused: $lane"
printf '.cursor/\n' > "$P1/.gitignore"
ok "the lane reports stack-codex-refused, a foreign Cursor rule and stack-cursor-refused"

echo "PASS: test_vault_context_sync_hosts"
