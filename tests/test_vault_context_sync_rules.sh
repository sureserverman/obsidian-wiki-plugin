#!/usr/bin/env bash
# test_vault_context_sync_rules.sh — sync-stack-rules.py copies every stack page in
# a vault into the stacks folder the session-start hook reads, removes copies an
# older release left in the Claude rules folder, and touches nothing it did not write.
#
# Every case runs against a fixture vault, a fixture stacks folder and a fixture
# CLAUDE_CONFIG_DIR, so the test says nothing about the machine it runs on and
# never writes to a real config.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SYNC="$ROOT/plugins/vault-context/scripts/sync-stack-rules.py"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$SYNC" ] || fail "missing $SYNC"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

V="$WORK/vault"; R="$WORK/stacks"; ST="$V/Portfolio/stacks"
CFG="$WORK/cfg"; L="$CFG/rules"
mkdir -p "$ST" "$R" "$L"
export CLAUDE_CONFIG_DIR="$CFG"
unset VAULT_CONTEXT_STACKS_DIR
echo "alpha source" > "$WORK/alpha-src.txt"
echo "beta source"  > "$WORK/beta-src.txt"

page() { # <slug> <paths-inline-list> <source> <body>
    printf -- '---\nstack: %s\npaths: %s\nsources: ["%s"]\nchecked: 2026-11-17\n---\n%s' \
        "$1" "$2" "$3" "$4" > "$ST/$1.md"
}
page alpha '["**/*.rs", "**/Cargo.toml"]' "$WORK/alpha-src.txt" $'# Alpha\n\nUse the alpha way.\n'
page beta  '["**/*.kt"]'                  "$WORK/beta-src.txt"  $'# Beta\n\nBeta facts.\n'

# A file the user owns in the same folder: never touched.
printf 'my own rule\n' > "$R/mine.md"
MINE_SUM="$(sha256sum "$R/mine.md" | cut -d' ' -f1)"

sync() { python3 "$SYNC" --vault "$V" --stacks-dir "$R" "$@"; }

# --- 1. first sync writes one copy per page ------------------------------------
out="$(sync 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "first sync exit $rc: $out"
for s in alpha beta; do
    [ -f "$R/vault-stack-$s.md" ] || fail "no rule written for $s"
done
echo "$out" | grep -qi 'wrote 2' || fail "summary does not say 'wrote 2': $out"
ok "first sync writes vault-stack-alpha.md and vault-stack-beta.md and says how many"

# Rule shape: frontmatter holding only paths, then the marker, then the body byte for byte.
python3 - "$ST" "$R" <<'EOF' || fail "rule shape"
import hashlib, json, re, sys
st, r = sys.argv[1], sys.argv[2]
for slug, globs in (("alpha", ["**/*.rs", "**/Cargo.toml"]), ("beta", ["**/*.kt"])):
    page = open(f"{st}/{slug}.md", "rb").read()
    body = page.split(b"\n---\n", 1)[1]
    rule = open(f"{r}/vault-stack-{slug}.md", "rb").read()
    assert rule.startswith(b"---\n"), f"{slug}: no frontmatter"
    fm, rest = rule[4:].split(b"\n---\n", 1)
    keys = [l.split(b":", 1)[0] for l in fm.split(b"\n") if l and not l.startswith((b" ", b"-"))]
    assert keys == [b"paths"], f"{slug}: frontmatter keys {keys}"
    m = re.match(rb"paths: (\[.*\])$", fm)
    assert m and json.loads(m.group(1)) == globs, f"{slug}: paths {fm!r}"
    marker, after = rest.split(b"\n", 1)
    want = "<!-- vault-context:stack-rule source=%s sha256=%s -->" % (slug, hashlib.sha256(page).hexdigest())
    assert marker.decode() == want, f"{slug}: marker {marker!r} != {want!r}"
    assert after == body, f"{slug}: body differs"
print("shape ok")
EOF
ok "each rule holds only paths, then the marker with the page's sha256, then the page body byte for byte"

out="$(sync --check 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "--check right after a sync exit $rc: $out"
ok "--check exits 0 right after a sync"

# --- 2. a page edit is drift until the next sync -------------------------------
page alpha '["**/*.rs", "**/Cargo.toml"]' "$WORK/alpha-src.txt" $'# Alpha\n\nUse the alpha way, edited.\n'
out="$(sync --check 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || fail "--check after a page edit exit $rc (want 1): $out"
echo "$out" | grep -q '^stale: alpha ' || fail "--check does not name the stale slug: $out"
echo "$out" | grep -q 'beta.*stale\|stale.*beta' && fail "--check calls beta stale: $out"
grep -q 'alpha way, edited' "$R/vault-stack-alpha.md" && fail "--check wrote the rule"
ok "after a page edit --check exits 1, names alpha and writes nothing"

out="$(sync --json --check 2>/dev/null)"
echo "$out" | jq -e '.pages[] | select(.slug=="alpha") | .state == "stale"' >/dev/null \
    || fail "--json does not report alpha stale: $out"
echo "$out" | jq -e '.pages[] | select(.slug=="beta") | .state == "in-sync"' >/dev/null \
    || fail "--json does not report beta in-sync: $out"
ok "--json reports alpha stale and beta in-sync"

out="$(sync 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "sync after edit exit $rc: $out"
echo "$out" | grep -qi 'updated 1' || fail "summary does not say 'updated 1': $out"
sync --check >/dev/null 2>&1 || fail "--check not 0 after re-sync"
grep -q 'alpha way, edited' "$R/vault-stack-alpha.md" || fail "rule does not carry the edit"
ok "a sync returns --check to 0 and the rule carries the edit"

# --- 3. a deleted page loses its rule ------------------------------------------
rm "$ST/beta.md"
out="$(sync --check 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || fail "--check with an orphan rule exit $rc (want 1): $out"
out="$(sync 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "sync after page delete exit $rc: $out"
[ -e "$R/vault-stack-beta.md" ] && fail "rule for the deleted page beta is still there"
echo "$out" | grep -qi 'removed 1' || fail "summary does not say 'removed 1': $out"
ok "after a page is deleted its rule is removed"

# --- 4. a vault-stack-* file the tool did not write is refused, untouched -------
printf -- '---\npaths: ["**/*.go"]\n---\nHand written.\n' > "$R/vault-stack-gamma.md"
GAMMA_SUM="$(sha256sum "$R/vault-stack-gamma.md" | cut -d' ' -f1)"
page alpha '["**/*.rs", "**/Cargo.toml"]' "$WORK/alpha-src.txt" $'# Alpha\n\nSecond edit.\n'
out="$(sync 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || fail "sync with a foreign vault-stack file exit $rc (want 1): $out"
echo "$out" | grep -q 'vault-stack-gamma.md' || fail "refusal does not name the file: $out"
[ "$(sha256sum "$R/vault-stack-gamma.md" | cut -d' ' -f1)" = "$GAMMA_SUM" ] \
    || fail "the foreign file changed"
grep -q 'Second edit' "$R/vault-stack-alpha.md" && fail "the run wrote rules despite the refusal"
ok "a hand-written vault-stack-gamma.md stops the run, is named, and stays byte-identical"
rm "$R/vault-stack-gamma.md"
sync >/dev/null 2>&1 || fail "sync after removing the foreign file"

# A symlink named like a rule is not ours, whatever it points at.
printf 'user file\n' > "$WORK/user-file.md"
USER_SUM="$(sha256sum "$WORK/user-file.md" | cut -d' ' -f1)"
mv "$R/vault-stack-alpha.md" "$WORK/alpha-rule.bak"
ln -s "$WORK/user-file.md" "$R/vault-stack-alpha.md"
out="$(sync 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || fail "sync with a symlinked vault-stack file exit $rc (want 1): $out"
[ -L "$R/vault-stack-alpha.md" ] || fail "the symlink was replaced"
[ "$(sha256sum "$WORK/user-file.md" | cut -d' ' -f1)" = "$USER_SUM" ] || fail "the symlink target changed"
rm "$R/vault-stack-alpha.md"; mv "$WORK/alpha-rule.bak" "$R/vault-stack-alpha.md"
ok "a symlink named vault-stack-alpha.md is refused and its target is untouched"

# A marker naming another slug is not this file's marker (a copied rule).
sed 's/source=alpha /source=beta /' "$R/vault-stack-alpha.md" > "$R/vault-stack-zeta.md"
ZETA_SUM="$(sha256sum "$R/vault-stack-zeta.md" | cut -d' ' -f1)"
out="$(sync 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || fail "sync with a mismatched marker exit $rc (want 1): $out"
echo "$out" | grep -q 'vault-stack-zeta.md' || fail "mismatched marker not named: $out"
[ "$(sha256sum "$R/vault-stack-zeta.md" | cut -d' ' -f1)" = "$ZETA_SUM" ] || fail "vault-stack-zeta.md changed"
rm "$R/vault-stack-zeta.md"
sync >/dev/null 2>&1 || fail "sync after removing the mismatched file"
ok "a rule whose marker names another slug is refused and untouched"

# --- 5. other files in the folder are never touched ----------------------------
[ "$(sha256sum "$R/mine.md" | cut -d' ' -f1)" = "$MINE_SUM" ] || fail "mine.md changed"
ok "mine.md in the stacks folder is never touched"

# --- 6. a missing vault deletes nothing ----------------------------------------
page beta '["**/*.kt"]' "$WORK/beta-src.txt" $'# Beta\n\nBeta facts.\n'
sync >/dev/null 2>&1 || fail "sync before missing-vault case"
[ -f "$R/vault-stack-alpha.md" ] && [ -f "$R/vault-stack-beta.md" ] || fail "setup: rules missing"
out="$(python3 "$SYNC" --vault "$WORK/no-such-vault" --stacks-dir "$R" 2>&1)"; rc=$?
[ "$rc" -eq 2 ] || fail "missing vault exit $rc (want 2): $out"
echo "$out" | grep -qi 'vault not reachable' || fail "missing vault message: $out"
[ -f "$R/vault-stack-alpha.md" ] && [ -f "$R/vault-stack-beta.md" ] \
    || fail "a missing vault deleted rules"
ok "--vault pointing at a missing folder exits 2 and both rules stay"

# A vault that shows no stack pages at all (no stacks folder, or an empty one) is
# a half-mounted or wrong vault as far as the tool can tell: it removes nothing.
mkdir -p "$WORK/bare-vault"
out="$(python3 "$SYNC" --vault "$WORK/bare-vault" --stacks-dir "$R" 2>&1)"; rc=$?
[ "$rc" -eq 2 ] || fail "vault without a stacks folder exit $rc (want 2): $out"
mkdir -p "$WORK/bare-vault/Portfolio/stacks"
out="$(python3 "$SYNC" --vault "$WORK/bare-vault" --stacks-dir "$R" 2>&1)"; rc=$?
[ "$rc" -eq 2 ] || fail "vault with an empty stacks folder exit $rc (want 2): $out"
[ -f "$R/vault-stack-alpha.md" ] && [ -f "$R/vault-stack-beta.md" ] \
    || fail "a vault with no pages deleted rules"
ok "a vault with no stacks folder, or an empty one, exits 2 and removes no rule"

# --- 7. --lint refuses a page whose sources path is gone, writing nothing --------
SNAP="$(cd "$R" && sha256sum * | sort)"
rm "$WORK/beta-src.txt"
page alpha '["**/*.rs", "**/Cargo.toml"]' "$WORK/alpha-src.txt" $'# Alpha\n\nThird edit.\n'
out="$(sync --lint 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || fail "--lint with a missing source exit $rc (want 1): $out"
echo "$out" | grep -q 'beta' || fail "--lint does not name beta: $out"
[ "$(cd "$R" && sha256sum * | sort)" = "$SNAP" ] || fail "--lint wrote to the stacks folder"
ok "--lint exits 1 on a page with a missing sources path and writes nothing"

# --- 8. --only scopes the run --------------------------------------------------
out="$(sync --lint --only alpha 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "--lint --only alpha exit $rc with only beta broken: $out"
ok "--lint --only alpha ignores a broken page beta"

# --- 9. an invalid page is refused by name and writes nothing for itself --------
printf -- '---\nstack: delta\nsources: ["%s"]\nchecked: 2026-11-17\n---\nNo paths.\n' \
    "$WORK/alpha-src.txt" > "$ST/delta.md"
out="$(sync --only delta 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || fail "page without paths exit $rc (want 1): $out"
echo "$out" | grep -q 'delta' || fail "refusal does not name the page: $out"
[ -e "$R/vault-stack-delta.md" ] && fail "a rule was written for the invalid page"
ok "a page with no paths is refused by name and gets no rule"

# In a full write run a refused page does not stop the others.
page alpha '["**/*.rs", "**/Cargo.toml"]' "$WORK/alpha-src.txt" $'# Alpha\n\nMixed-run edit.\n'
out="$(sync 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || fail "write run with one refused page exit $rc (want 1): $out"
grep -q 'Mixed-run edit' "$R/vault-stack-alpha.md" || fail "the valid page was not synced beside the refused one"
[ -e "$R/vault-stack-delta.md" ] && fail "a rule was written for the refused page in a full run"
ok "in a full run the refused page gets no rule and the valid pages still sync"

# --- 10. usage refusals --------------------------------------------------------
out="$(sync --host cursor 2>&1)"; rc=$?
[ "$rc" -eq 2 ] || fail "--host cursor exit $rc (want 2): $out"
out="$(sync --only '../x' 2>&1)"; rc=$?
[ "$rc" -eq 2 ] || fail "--only with a path exit $rc (want 2): $out"
ok "an unsupported --host and a non-slug --only exit 2"

# --- 11. a stacks folder that cannot be written is exit 2, not drift --------------
rm "$ST/delta.md"
chmod 0555 "$R"
page alpha '["**/*.rs", "**/Cargo.toml"]' "$WORK/alpha-src.txt" $'# Alpha\n\nFourth edit.\n'
out="$(sync 2>&1)"; rc=$?
chmod 0755 "$R"
if [ "$(id -u)" != 0 ]; then
    [ "$rc" -eq 2 ] || fail "unwritable stacks folder exit $rc (want 2): $out"
    echo "$out" | grep -qi 'file-system error' || fail "unwritable stacks folder message: $out"
    ok "an unwritable stacks folder exits 2 with a file-system error"
fi
sync >/dev/null 2>&1 || fail "sync after the unwritable-folder case"

# --- 12. the stacks folder: env, then ${CLAUDE_CONFIG_DIR}/vault-stacks ----------
E="$WORK/env-stacks"
out="$(VAULT_CONTEXT_STACKS_DIR="$E" python3 "$SYNC" --vault "$V" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "sync with VAULT_CONTEXT_STACKS_DIR exit $rc: $out"
[ -f "$E/vault-stack-alpha.md" ] || fail "VAULT_CONTEXT_STACKS_DIR not used: $out"
cmp -s "$E/vault-stack-alpha.md" "$R/vault-stack-alpha.md" || fail "copy bytes differ between folders"
out="$(python3 "$SYNC" --vault "$V" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "sync with the default folder exit $rc: $out"
[ -f "$CFG/vault-stacks/vault-stack-alpha.md" ] || fail "default folder \$CLAUDE_CONFIG_DIR/vault-stacks not used: $out"
echo "$out" | grep -qF "$CFG/vault-stacks" || fail "summary does not name the stacks folder: $out"
[ -e "$L/vault-stack-alpha.md" ] && fail "the sync wrote into the rules folder"
ok "VAULT_CONTEXT_STACKS_DIR, else \$CLAUDE_CONFIG_DIR/vault-stacks, gets the same bytes; the rules folder gets none"

# --- 13. a marked copy left in the rules folder is legacy: --check drift, removed --
cp "$R/vault-stack-alpha.md" "$L/vault-stack-alpha.md"
printf 'my own rule\n' > "$L/mine.md"
LMINE_SUM="$(sha256sum "$L/mine.md" | cut -d' ' -f1)"
out="$(sync --check 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || fail "--check with a legacy copy exit $rc (want 1): $out"
echo "$out" | grep -qF "legacy: alpha ($L/vault-stack-alpha.md)" || fail "--check does not report legacy alpha: $out"
[ -f "$L/vault-stack-alpha.md" ] || fail "--check removed the legacy copy"
out="$(sync --check --json 2>/dev/null)"
echo "$out" | jq -e --arg p "$L/vault-stack-alpha.md" '.legacy == [{"slug":"alpha","rule":$p}]' >/dev/null \
    || fail "--json does not list the legacy copy: $out"
ok "a marked vault-stack-alpha.md in the rules folder is --check drift 'legacy' and stays put"

out="$(sync 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "sync with a legacy copy exit $rc: $out"
[ -e "$L/vault-stack-alpha.md" ] && fail "the legacy copy is still in the rules folder"
echo "$out" | grep -qi 'removed 1' || fail "summary does not count the legacy copy under removed: $out"
[ "$(sha256sum "$L/mine.md" | cut -d' ' -f1)" = "$LMINE_SUM" ] || fail "mine.md in the rules folder changed"
sync --check >/dev/null 2>&1 || fail "--check not 0 once the legacy copy is gone"
ok "a write run removes the legacy copy, counts it under removed, and leaves the rules folder's other files"

# A vault showing no stack pages removes no legacy copy either.
cp "$R/vault-stack-alpha.md" "$L/vault-stack-alpha.md"
out="$(python3 "$SYNC" --vault "$WORK/bare-vault" --stacks-dir "$WORK/empty-stacks" 2>&1)"; rc=$?
[ "$rc" -eq 2 ] || fail "empty vault with a legacy copy exit $rc (want 2): $out"
[ -f "$L/vault-stack-alpha.md" ] || fail "an empty vault removed the legacy copy"
rm "$L/vault-stack-alpha.md"
ok "a vault with no stack pages exits 2 and removes no legacy copy"

# A foreign vault-stack-*.md in the rules folder still stops every mode, untouched.
printf -- '---\npaths: ["**/*.go"]\n---\nHand written.\n' > "$L/vault-stack-go.md"
GO_SUM="$(sha256sum "$L/vault-stack-go.md" | cut -d' ' -f1)"
page alpha '["**/*.rs", "**/Cargo.toml"]' "$WORK/alpha-src.txt" $'# Alpha\n\nFifth edit.\n'
for mode in "" --check --lint "--only alpha"; do
    # shellcheck disable=SC2086
    out="$(sync $mode 2>&1)"; rc=$?
    [ "$rc" -eq 1 ] || fail "foreign file in the rules folder, mode '$mode': exit $rc (want 1): $out"
    echo "$out" | grep -qF "$L/vault-stack-go.md" || fail "mode '$mode' does not name the foreign file: $out"
done
grep -q 'Fifth edit' "$R/vault-stack-alpha.md" && fail "a write run wrote despite the foreign file"
[ "$(sha256sum "$L/vault-stack-go.md" | cut -d' ' -f1)" = "$GO_SUM" ] || fail "the foreign file changed"
rm "$L/vault-stack-go.md"
ok "a foreign vault-stack-go.md in the rules folder stops every mode and stays byte-identical"

# A refused page keeps its legacy copy: nothing else would deliver it.
sync >/dev/null 2>&1
cp "$R/vault-stack-alpha.md" "$L/vault-stack-alpha.md"
ALPHA_PAGE="$(cat "$ST/alpha.md")"
printf -- '---\nstack: alpha\nsources: ["%s"]\nchecked: 2026-11-17\n---\nNo paths.\n' "$WORK/alpha-src.txt" > "$ST/alpha.md"
out="$(sync 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || fail "write run with a refused page exit $rc (want 1): $out"
[ -f "$L/vault-stack-alpha.md" ] || fail "the legacy copy of a refused page was removed: $out"
printf '%s' "$ALPHA_PAGE" > "$ST/alpha.md"
sync >/dev/null 2>&1
[ -e "$L/vault-stack-alpha.md" ] && fail "the legacy copy stayed after its page parsed again"
ok "a refused page keeps its legacy copy; it goes once the page parses again"

echo "PASS: test_vault_context_sync_rules.sh"
