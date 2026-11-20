#!/usr/bin/env bash
# test_vault_context_target_cursor.sh — lib/stack_target_cursor.py writes one
# Cursor rule per applying stack under the project root's .cursor/rules/, removes
# rules whose stack no longer applies or whose page is gone, refuses projects
# where git would commit the rule, skips area directories and missing folders,
# and touches no file it did not write.
#
# Every case runs against fixture projects, a fixture vault, a fixture registry
# and an empty git config, so the test says nothing about the machine it runs on.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$ROOT/plugins/vault-context/scripts/lib"
MOD="$LIB/stack_target_cursor.py"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$MOD" ] || fail "missing $MOD"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Isolate git from the owner's config: no global excludes, no init template.
mkdir -p "$WORK/xdg"
: > "$WORK/gitconfig"
export GIT_CONFIG_GLOBAL="$WORK/gitconfig" GIT_CONFIG_NOSYSTEM=1 XDG_CONFIG_HOME="$WORK/xdg"
gitinit() { git init -q --template= "$1"; }

ST="$WORK/vault/Portfolio/stacks"
mkdir -p "$ST"
echo "source" > "$WORK/src.txt"
page() { # <slug> <paths-inline-list> <body>
    printf -- '---\nstack: %s\npaths: %s\nsources: ["%s"]\nchecked: 2026-11-17\n---\n%s' \
        "$1" "$2" "$WORK/src.txt" "$3" > "$ST/$1.md"
}
page alpha '["**/*.rs"]' $'# Alpha\n\nUse the alpha way.\n'
page beta  '["*.kt"]'    $'# Beta\n\nBeta facts.\n'
page delta '["*.md"]'    $'# Delta\n\nDocs facts.\n'

# Registry: area/ holds two registered projects; mono/sub is registered below its
# repo's top level; plain/ is a registered folder that is not a git repo.
export VAULT_CONTEXT_REGISTRY="$WORK/registry.yaml"
cat > "$VAULT_CONTEXT_REGISTRY" <<EOF
projects:
  - name: proj-a
    path: $WORK/area/proj-a
  - name: proj-b
    path: $WORK/area/proj-b
  - name: sub
    path: $WORK/mono/sub
  - name: plain
    path: $WORK/plain
EOF

cat > "$WORK/drive.py" <<'EOF'
import hashlib, os, sys
sys.dont_write_bytecode = True
lib, mode, project, st = sys.argv[1:5]
sys.path.insert(0, lib)
import stack_target_cursor as c
from stack_pages import load_page
pages = []
for n in sorted(os.listdir(st)):
    if n.endswith(".md"):
        p = os.path.join(st, n)
        with open(p, "rb") as f:
            pages.append((load_page(p), hashlib.sha256(f.read()).hexdigest()))
if mode == "apply":
    r = c.apply(c.plan(project, pages))
else:
    r = c.check(project, pages)
for m in r["messages"]:
    print(m)
print("status=" + r["status"])
if mode == "check" and r["status"] == "ok":
    print("in_sync=" + str(r["in_sync"]))
EOF
cursor() { python3 "$WORK/drive.py" "$LIB" "$@" "$ST" 2>&1; }

# --- 1. a project with src/main.rs and README.md --------------------------------
P="$WORK/p1"; RD="$P/.cursor/rules"
mkdir -p "$P/src" "$RD"
gitinit "$P"
printf '.cursor/\n' > "$P/.gitignore"
echo 'fn main() {}' > "$P/src/main.rs"
echo '# p1' > "$P/README.md"
git -C "$P" add .gitignore src/main.rs README.md
printf 'my own rule\n' > "$RD/mine.mdc"
touch -d '2020-01-01' "$RD/mine.mdc"
MINE="$(stat -c '%Y %s' "$RD/mine.mdc") $(sha256sum < "$RD/mine.mdc")"

out="$(cursor apply "$P")"
echo "$out" | grep -q 'status=ok' || fail "first apply: $out"
[ -f "$RD/vault-stack-alpha.mdc" ] || fail "no vault-stack-alpha.mdc: $out"
[ -f "$RD/vault-stack-delta.mdc" ] || fail "no vault-stack-delta.mdc: $out"
[ ! -e "$RD/vault-stack-beta.mdc" ] || fail "beta (*.kt) written though no .kt file exists"
python3 - "$ST" "$RD" <<'EOF' || fail "rule shape"
import hashlib, sys
st, rd = sys.argv[1], sys.argv[2]
for slug, globs in (("alpha", "**/*.rs"), ("delta", "**/*.md")):
    page = open(f"{st}/{slug}.md", "rb").read()
    body = page.split(b"\n---\n", 1)[1]
    want = (f"---\ndescription: Owner rules for {slug} files (generated from the vault)\n"
            f"globs: {globs}\nalwaysApply: false\n---\n"
            f"<!-- vault-context:stack-rule source={slug} sha256={hashlib.sha256(page).hexdigest()} -->\n"
            ).encode() + body
    got = open(f"{rd}/vault-stack-{slug}.mdc", "rb").read()
    assert got == want, f"{slug}:\n{got!r}\n!=\n{want!r}"
EOF
ok "vault-stack-alpha.mdc holds description, globs: **/*.rs, alwaysApply: false, the marker and the body; no beta rule"
ok "a page pattern *.md is written as **/*.md"

out="$(cursor check "$P")"
echo "$out" | grep -q 'in_sync=True' || fail "check right after apply: $out"
ok "check right after apply reports in sync"

# --- 2. a page edit is reported stale by check, then updated ---------------------
page alpha '["**/*.rs"]' $'# Alpha\n\nUse the alpha way, edited.\n'
out="$(cursor check "$P")"
echo "$out" | grep -q 'in_sync=False' || fail "check after page edit: $out"
echo "$out" | grep -q '^stale: alpha' || fail "check does not name alpha stale: $out"
grep -q 'alpha way, edited' "$RD/vault-stack-alpha.mdc" && fail "check wrote the rule"
out="$(cursor apply "$P")"
grep -q 'alpha way, edited' "$RD/vault-stack-alpha.mdc" || fail "apply did not update alpha: $out"
ok "check reports a stale rule after a page edit; apply updates it"

# --- 3. a stack that stops applying, and a page that is gone ---------------------
git -C "$P" rm -q --cached src/main.rs; rm "$P/src/main.rs"
out="$(cursor check "$P")"
echo "$out" | grep -q 'in_sync=False' || fail "check after main.rs removed: $out"
out="$(cursor apply "$P")"
[ ! -e "$RD/vault-stack-alpha.mdc" ] || fail "alpha rule kept after src/main.rs removed: $out"
ok "after src/main.rs is removed the alpha rule is removed"

mv "$ST/delta.md" "$WORK/delta.md.away"
out="$(cursor apply "$P")"
[ ! -e "$RD/vault-stack-delta.mdc" ] || fail "delta rule kept after its page is gone: $out"
mv "$WORK/delta.md.away" "$ST/delta.md"
ok "a rule whose page is gone is removed"

# --- 4. an unmarked vault-stack-*.mdc stops the run for that project -------------
echo 'fn main() {}' > "$P/src/main.rs"; git -C "$P" add src/main.rs
printf -- '---\nglobs: **/*.go\n---\nhand written\n' > "$RD/vault-stack-gamma.mdc"
GAMMA="$(sha256sum < "$RD/vault-stack-gamma.mdc")"
out="$(cursor apply "$P")"
echo "$out" | grep -q 'status=refused' || fail "unmarked gamma did not stop the run: $out"
echo "$out" | grep -q 'vault-stack-gamma.mdc' || fail "refusal does not name gamma: $out"
[ "$(sha256sum < "$RD/vault-stack-gamma.mdc")" = "$GAMMA" ] || fail "gamma changed"
[ ! -e "$RD/vault-stack-alpha.mdc" ] || fail "alpha written despite the refusal"
out="$(cursor check "$P")"
echo "$out" | grep -q 'status=refused' || fail "check does not refuse with gamma present: $out"
rm "$RD/vault-stack-gamma.mdc"
out="$(cursor apply "$P")"
[ -f "$RD/vault-stack-alpha.mdc" ] || fail "alpha not written once gamma is gone: $out"
ok "a hand-written vault-stack-gamma.mdc stops the run, named and unchanged"

[ "$(stat -c '%Y %s' "$RD/mine.mdc") $(sha256sum < "$RD/mine.mdc")" = "$MINE" ] \
    || fail "mine.mdc was touched"
ok "another file in .cursor/rules/ is never touched"

# --- 5. a project where git would commit the rule is refused ---------------------
P2="$WORK/p2"; mkdir -p "$P2/src"; gitinit "$P2"
printf 'target/\n' > "$P2/.gitignore"
echo 'fn main() {}' > "$P2/src/main.rs"; git -C "$P2" add .gitignore src/main.rs
out="$(cursor apply "$P2")"
echo "$out" | grep -q 'status=refused' || fail "unignored .cursor not refused: $out"
echo "$out" | grep -q 'would be committed' || fail "refusal lacks 'would be committed': $out"
[ -z "$(find "$P2" -name 'vault-stack-*' 2>/dev/null)" ] || fail "a rule was written where git would track it"
ok "a project whose .gitignore lacks .cursor/ is refused and gets no file"

P3="$WORK/p3"; mkdir -p "$P3/src" "$P3/.cursor/rules"; gitinit "$P3"
printf '.cursor/\n' > "$P3/.gitignore"
echo 'fn main() {}' > "$P3/src/main.rs"
echo 'team rule' > "$P3/.cursor/rules/team.mdc"
git -C "$P3" add .gitignore src/main.rs; git -C "$P3" add -f .cursor/rules/team.mdc
out="$(cursor apply "$P3")"
echo "$out" | grep -q 'would be committed' || fail "tracked .cursor not refused: $out"
[ ! -e "$P3/.cursor/rules/vault-stack-alpha.mdc" ] || fail "a rule was written into a tracked .cursor"
ok "a project that tracks .cursor/ is refused"

# --- 6. area directories and missing folders are skipped ------------------------
mkdir -p "$WORK/area/proj-a" "$WORK/area/proj-b"
echo 'fn main() {}' > "$WORK/area/x.rs"
out="$(cursor apply "$WORK/area")"
echo "$out" | grep -q 'status=skipped' || fail "area directory not skipped: $out"
echo "$out" | grep -q 'area directory' || fail "skip line does not say area directory: $out"
[ ! -e "$WORK/area/.cursor" ] || fail "something written in the area directory"
out="$(cursor apply "$WORK/nope")"
echo "$out" | grep -q 'status=skipped' || fail "missing folder not skipped: $out"
echo "$out" | grep -q "$WORK/nope" || fail "skip line does not name the missing folder: $out"
ok "an area directory and a missing folder are skipped with a line saying so"

# --- 7. a registered folder below its git top level ------------------------------
M="$WORK/mono"; mkdir -p "$M/sub" "$M/lib"; gitinit "$M"
printf '.cursor/\n' > "$M/.gitignore"
echo 'fn x() {}' > "$M/lib/top.rs"; echo '# sub' > "$M/sub/notes.txt"
git -C "$M" add .gitignore lib/top.rs sub/notes.txt
out="$(cursor apply "$M/sub")"
echo "$out" | grep -q 'status=ok' || fail "mono/sub apply: $out"
[ -f "$M/.cursor/rules/vault-stack-alpha.mdc" ] || fail "no alpha rule under the top level: $out"
[ ! -e "$M/sub/.cursor" ] || fail "rule written under the registered folder"
ok "a registered folder below its git top level gets its rule under the top level, matched on its files"

# --- 8. outside git there is nothing to commit ------------------------------------
mkdir -p "$WORK/plain"; echo 'fn main() {}' > "$WORK/plain/m.rs"
out="$(cursor apply "$WORK/plain")"
echo "$out" | grep -q 'status=ok' || fail "plain folder apply: $out"
[ -f "$WORK/plain/.cursor/rules/vault-stack-alpha.mdc" ] || fail "no rule in a non-git project: $out"
ok "a registered folder outside git gets its rule"

# --- 9. glob translation ----------------------------------------------------------
python3 - "$LIB" <<'EOF' || fail "glob translation"
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
import stack_target_cursor as c
assert c.cursor_globs(["*.{ts,tsx}", "src/*.rs"]) == "**/*.ts,**/*.tsx,src/*.rs", c.cursor_globs(["*.{ts,tsx}", "src/*.rs"])
try:
    c.cursor_globs(["/*.md"])
except ValueError:
    pass
else:
    raise AssertionError("/*.md accepted")
EOF
ok "braces expand into separate globs; a top-level-only pattern is refused"

# --- review: a comma outside braces has no Cursor form -------------------------
ROOT_DIR="$ROOT" python3 - <<'EOF' || fail "a comma glob was not refused"
import os, sys
sys.path.insert(0, os.path.join(os.environ.get("ROOT_DIR", "."), "plugins/vault-context/scripts/lib"))
import stack_target_cursor as T
try:
    T.cursor_globs(["**/a,b.rs"])
except ValueError:
    sys.exit(0)
sys.exit(1)
EOF
ok "a pattern holding a comma outside braces is refused for Cursor"

echo "PASS: test_vault_context_target_cursor"
