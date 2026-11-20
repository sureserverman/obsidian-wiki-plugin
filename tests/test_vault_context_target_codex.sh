#!/usr/bin/env bash
# test_vault_context_target_codex.sh — the Codex target writes one marked copy per
# stack page under <codex-home>/vault-stacks/ and one pointer block in the home's
# AGENTS file, keeps every byte outside the block, and refuses what it cannot parse.
#
# Every case runs against a fixture vault and a fixture Codex home; HOME points
# into the fixture and CODEX_HOME is unset, so nothing can reach a real ~/.codex.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$ROOT/plugins/vault-context/scripts/lib"
MOD="$LIB/stack_target_codex.py"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$MOD" ] || fail "missing $MOD"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export HOME="$WORK/home"
mkdir -p "$HOME"
unset CODEX_HOME

V="$WORK/vault"; ST="$V/Portfolio/stacks"
mkdir -p "$ST"
echo "source" > "$WORK/src.txt"

START='<!-- vault-context:stacks:start -->'
END='<!-- vault-context:stacks:end -->'

page() { # <slug> <paths-inline-list> <body>
    printf -- '---\nstack: %s\npaths: %s\nsources: ["%s"]\nchecked: 2026-11-17\n---\n%s' \
        "$1" "$2" "$WORK/src.txt" "$3" > "$ST/$1.md"
}

# The harness: load every page in $ST, then write (plan + apply) or check.
# A refusal prints the module's message and exits 1; check exits 1 on drift.
cat > "$WORK/drive.py" <<'EOF'
import json, os, sys
sys.dont_write_bytecode = True
sys.path.insert(0, os.environ["LIB"])
import stack_target_codex as T
from stack_pages import load_page
mode, home, st = sys.argv[1], sys.argv[2], sys.argv[3]
pages = [load_page(os.path.join(st, n)) for n in sorted(os.listdir(st)) if n.endswith(".md")]
try:
    if mode == "write":
        res = T.apply(T.plan(home, pages))
        print(json.dumps(res, sort_keys=True))
        sys.exit(0)
    res = T.check(home, pages)
    print(json.dumps(res, sort_keys=True))
    sys.exit(0 if res["in_sync"] else 1)
except T.CodexTargetError as e:
    print(f"refused: {e}", file=sys.stderr)
    sys.exit(1)
EOF
export LIB
run() { python3 "$WORK/drive.py" "$1" "$2" "$ST"; }
sum() { sha256sum "$1" | cut -d' ' -f1; }
# The file with the block's lines (start marker through end marker) taken out.
outside() { python3 - "$1" <<'EOF'
import sys
data = open(sys.argv[1], "rb").read()
lines = data.split(b"\n")
s = lines.index(b"<!-- vault-context:stacks:start -->")
e = lines.index(b"<!-- vault-context:stacks:end -->")
sys.stdout.buffer.write(b"\n".join(lines[:s] + lines[e + 1:]))
EOF
}
block() { python3 - "$1" <<'EOF'
import sys
data = open(sys.argv[1], "rb").read()
lines = data.split(b"\n")
s = lines.index(b"<!-- vault-context:stacks:start -->")
e = lines.index(b"<!-- vault-context:stacks:end -->")
sys.stdout.buffer.write(b"\n".join(lines[s:e + 1]) + b"\n")
EOF
}

page alpha '["**/*.rs", "**/Cargo.toml"]' $'# Alpha\n\nUse the alpha way.\n'

# --- 1. no AGENTS file: AGENTS.md holds only the block; the copy holds marker + body
H="$WORK/codex1"; mkdir -p "$H"
out="$(run write "$H" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "first write exit $rc: $out"
[ -f "$H/AGENTS.md" ] || fail "AGENTS.md was not created"
[ -e "$H/AGENTS.override.md" ] && fail "AGENTS.override.md was created"
python3 - "$H" "$ST" <<'EOF' || fail "AGENTS.md / copy shape"
import hashlib, sys
h, st = sys.argv[1], sys.argv[2]
agents = open(f"{h}/AGENTS.md", "rb").read().decode()
lines = agents.split("\n")
assert lines[0] == "<!-- vault-context:stacks:start -->", f"line 1 {lines[0]!r}"
assert agents.endswith("<!-- vault-context:stacks:end -->\n"), f"tail {agents[-60:]!r}"
assert agents.count("vault-context:stacks:start") == 1 and agents.count("vault-context:stacks:end") == 1
assert "## Stack rules" in lines, "no heading"
assert ("Before you read or edit a file that matches a pattern below, read the page next "
        "to it and follow it.") in lines, "no instruction line"
copy = f"{h}/vault-stacks/alpha.md"
assert any("`**/*.rs`" in l and "`**/Cargo.toml`" in l and l.endswith(copy) for l in lines), \
    f"no pointer line for alpha -> {copy}: {agents!r}"
page = open(f"{st}/alpha.md", "rb").read()
body = page.split(b"\n---\n", 1)[1]
got = open(copy, "rb").read()
marker, rest = got.split(b"\n", 1)
want = "<!-- vault-context:stack-rule source=alpha sha256=%s -->" % hashlib.sha256(page).hexdigest()
assert marker.decode() == want, f"marker {marker!r} != {want!r}"
assert rest == body, "copy body differs from the page body"
EOF
out="$(run check "$H" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "check right after a write exit $rc: $out"
ok "no AGENTS file: AGENTS.md holds only the block, vault-stacks/alpha.md holds the marker and the page body, check is clean"

# --- 2. an AGENTS.md with other text keeps every byte outside the block -------
H="$WORK/codex2"; mkdir -p "$H"
printf '# My Codex notes\n\nAlways run the tests.\n' > "$H/AGENTS.md"
chmod 600 "$H/AGENTS.md"
cp "$H/AGENTS.md" "$WORK/expect2"
run write "$H" >/dev/null 2>&1 || fail "write into an owner AGENTS.md"
outside "$H/AGENTS.md" > "$WORK/got2"
cmp -s "$WORK/got2" "$WORK/expect2" || fail "text outside the block changed after the first write"
[ "$(stat -c %a "$H/AGENTS.md")" = 600 ] || fail "file mode changed after the first write"
# The owner adds text after the block and before it; then a page changes and one is added.
python3 - "$H/AGENTS.md" <<'EOF'
import sys
p = sys.argv[1]
d = open(p, "rb").read()
open(p, "wb").write(b"Owner header line.\n" + d + b"\nTrailing owner note, no newline at end")
EOF
{ printf 'Owner header line.\n'; cat "$WORK/expect2"; printf '\nTrailing owner note, no newline at end'; } > "$WORK/expect2b"
page alpha '["**/*.rs", "**/Cargo.toml"]' $'# Alpha\n\nUse the alpha way, edited.\n'
page beta '["*.kt"]' $'# Beta\n\nBeta facts.\n'
run write "$H" >/dev/null 2>&1 || fail "update write"
outside "$H/AGENTS.md" > "$WORK/got2b"
cmp -s "$WORK/got2b" "$WORK/expect2b" || fail "text outside the block changed after an update"
block "$H/AGENTS.md" | grep -qF "$H/vault-stacks/beta.md" || fail "the update did not add beta's line"
grep -q 'edited' "$H/vault-stacks/alpha.md" || fail "the update did not refresh alpha's copy"
[ "$(stat -c %a "$H/AGENTS.md")" = 600 ] || fail "file mode changed after an update"
mkdir -p "$WORK/empty-stacks"
python3 "$WORK/drive.py" write "$H" "$WORK/empty-stacks" >/dev/null 2>&1 || fail "removal write"
[ -f "$H/AGENTS.md" ] || fail "an owner AGENTS.md was deleted on removal"
cmp -s "$H/AGENTS.md" "$WORK/expect2b" || fail "AGENTS.md is not byte-identical to the owner's text after the block's removal"
[ -e "$H/vault-stacks/alpha.md" ] && fail "alpha's copy stayed after every page went"
ok "an owner AGENTS.md keeps every byte outside the block through a first write, an update and a removal"

# --- 3. a non-empty AGENTS.override.md gets the block; AGENTS.md is untouched -
H="$WORK/codex3"; mkdir -p "$H"
printf 'base instructions\n' > "$H/AGENTS.md"
printf 'override instructions\n' > "$H/AGENTS.override.md"
BASE_SUM="$(sum "$H/AGENTS.md")"
run write "$H" >/dev/null 2>&1 || fail "write with an override present"
grep -qxF "$START" "$H/AGENTS.override.md" || fail "the block is not in AGENTS.override.md"
[ "$(sum "$H/AGENTS.md")" = "$BASE_SUM" ] || fail "AGENTS.md changed although the override is the file Codex reads"
ok "a non-empty AGENTS.override.md gets the block and AGENTS.md stays byte-identical"

# An empty override is not the file Codex reads: the block goes to AGENTS.md.
H="$WORK/codex3b"; mkdir -p "$H"
: > "$H/AGENTS.override.md"
run write "$H" >/dev/null 2>&1 || fail "write with an empty override"
grep -qxF "$START" "$H/AGENTS.md" || fail "an empty override took the block"
[ -s "$H/AGENTS.override.md" ] && fail "the empty override was written to"
ok "an empty AGENTS.override.md is passed over for AGENTS.md"

# --- 4. a broken marker pair, or two blocks, is refused and the file unchanged
for shape in start-only end-only two-blocks; do
    H="$WORK/codex4-$shape"; mkdir -p "$H"
    case "$shape" in
        start-only) printf 'mine\n%s\nhalf a block\n' "$START" > "$H/AGENTS.md" ;;
        end-only)   printf 'mine\n%s\n' "$END" > "$H/AGENTS.md" ;;
        two-blocks) printf '%s\none\n%s\nmine\n%s\ntwo\n%s\n' "$START" "$END" "$START" "$END" > "$H/AGENTS.md" ;;
    esac
    BEFORE="$(sum "$H/AGENTS.md")"
    out="$(run write "$H" 2>&1)"; rc=$?
    [ "$rc" -eq 1 ] || fail "$shape: write exit $rc (want 1): $out"
    echo "$out" | grep -qF "$H/AGENTS.md" || fail "$shape: refusal does not name the file: $out"
    [ "$(sum "$H/AGENTS.md")" = "$BEFORE" ] || fail "$shape: AGENTS.md changed"
    [ -e "$H/vault-stacks" ] && fail "$shape: copies were written despite the refusal"
    out="$(run check "$H" 2>&1)"; rc=$?
    [ "$rc" -eq 1 ] || fail "$shape: check exit $rc (want 1): $out"
done
ok "a start marker with no end, an end with no start, and two blocks each exit 1 and leave AGENTS.md unchanged"

# --- 5. a copy whose page is gone is removed and its line leaves the block ----
H="$WORK/codex5"; mkdir -p "$H"
run write "$H" >/dev/null 2>&1 || fail "write alpha+beta"
[ -f "$H/vault-stacks/beta.md" ] || fail "setup: no beta copy"
mv "$ST/beta.md" "$WORK/beta.page"
out="$(run check "$H" 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || fail "check with an orphan copy exit $rc (want 1): $out"
run write "$H" >/dev/null 2>&1 || fail "write after beta's page went"
[ -e "$H/vault-stacks/beta.md" ] && fail "beta's copy stayed after its page went"
grep -qF 'vault-stacks/beta.md' "$H/AGENTS.md" && fail "beta's line stayed in the block"
grep -qF "$H/vault-stacks/alpha.md" "$H/AGENTS.md" || fail "alpha's line left the block"
mv "$WORK/beta.page" "$ST/beta.md"
ok "a copy whose page is gone is removed and its line leaves the block"

# --- 6. an unmarked .md in vault-stacks/ stops the run ------------------------
H="$WORK/codex6"; mkdir -p "$H/vault-stacks"
printf 'hand written\n' > "$H/vault-stacks/gamma.md"
printf 'not markdown\n' > "$H/vault-stacks/notes.txt"
G_SUM="$(sum "$H/vault-stacks/gamma.md")"
out="$(run write "$H" 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || fail "write with an unmarked copy exit $rc (want 1): $out"
echo "$out" | grep -qF "$H/vault-stacks/gamma.md" || fail "refusal does not name gamma.md: $out"
[ "$(sum "$H/vault-stacks/gamma.md")" = "$G_SUM" ] || fail "gamma.md changed"
[ -e "$H/vault-stacks/alpha.md" ] && fail "a copy was written despite the refusal"
[ -e "$H/AGENTS.md" ] && fail "AGENTS.md was written despite the refusal"
# A marker naming another slug is not this file's marker.
rm "$H/vault-stacks/gamma.md"
run write "$WORK/codex1" >/dev/null 2>&1 || fail "refresh codex1"
sed 's/source=alpha /source=zeta /' "$WORK/codex1/vault-stacks/alpha.md" > "$H/vault-stacks/alpha.md"
out="$(run write "$H" 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || fail "write with a mismatched marker exit $rc (want 1): $out"
echo "$out" | grep -qF "$H/vault-stacks/alpha.md" || fail "mismatched marker not named: $out"
ok "an unmarked or mismarked .md in vault-stacks/ stops the run, named and unchanged"

# --- 7. the block is under 2,048 bytes for eight pages ------------------------
V8="$WORK/vault8/Portfolio/stacks"; mkdir -p "$V8"
i=0
for s in android-build android-icons android-store-metadata readme rust python-packaging debian-packaging firefox-extension; do
    i=$((i + 1))
    printf -- '---\nstack: %s\npaths: ["**/*.gradle.kts", "**/AndroidManifest.xml", "**/build.gradle"]\nsources: ["%s"]\nchecked: 2026-11-17\n---\nBody %s.\n' \
        "$s" "$WORK/src.txt" "$i" > "$V8/$s.md"
done
H="$WORK/codex7-with-a-longer-home-name/.codex"; mkdir -p "$H"
python3 "$WORK/drive.py" write "$H" "$V8" >/dev/null 2>&1 || fail "write eight pages"
n="$(block "$H/AGENTS.md" | wc -c)"
[ "$(block "$H/AGENTS.md" | grep -c 'vault-stacks/')" -eq 8 ] || fail "the block does not list eight pages"
[ "$n" -lt 2048 ] || fail "the block for eight pages is $n bytes (want < 2048)"
ok "the block for eight pages is $n bytes, under 2,048"

# --- 8. no pages: the block goes, and an AGENTS.md this tool created is deleted
H="$WORK/codex8"; mkdir -p "$H"
run write "$H" >/dev/null 2>&1 || fail "write before the removal case"
[ -f "$H/AGENTS.md" ] || fail "setup: no AGENTS.md"
printf 'kept\n' > "$H/vault-stacks/other.txt"
python3 "$WORK/drive.py" write "$H" "$WORK/empty-stacks" >/dev/null 2>&1 || fail "removal write"
[ -e "$H/AGENTS.md" ] && fail "the AGENTS.md this tool created is still there, now empty"
ls "$H/vault-stacks"/*.md >/dev/null 2>&1 && fail "copies stayed after every page went"
[ -f "$H/vault-stacks/other.txt" ] || fail "a non-.md file in vault-stacks/ was removed"
out="$(python3 "$WORK/drive.py" check "$H" "$WORK/empty-stacks" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || fail "check after the removal exit $rc: $out"
ok "with no pages the block is removed and the AGENTS.md this tool created is deleted"

# --- 9. check reports a stale copy and a stale block after a page edit, writing nothing
H="$WORK/codex9"; mkdir -p "$H"
run write "$H" >/dev/null 2>&1 || fail "write before the check case"
A_SUM="$(sum "$H/AGENTS.md")"; C_SUM="$(sum "$H/vault-stacks/alpha.md")"
page alpha '["**/*.rs", "**/Cargo.toml", "**/build.rs"]' $'# Alpha\n\nThird edit.\n'
out="$(run check "$H" 2>/dev/null)"; rc=$?
[ "$rc" -eq 1 ] || fail "check after a page edit exit $rc (want 1): $out"
echo "$out" | jq -e '.findings[] | select(.code=="stack-codex-copy-stale" and .slug=="alpha")' >/dev/null \
    || fail "check does not report alpha's copy stale: $out"
echo "$out" | jq -e '.findings[] | select(.code=="stack-codex-block-stale")' >/dev/null \
    || fail "check does not report the block stale: $out"
echo "$out" | jq -e '[.findings[] | select(.slug=="beta")] | length == 0' >/dev/null \
    || fail "check reports beta although it did not change: $out"
[ "$(sum "$H/AGENTS.md")" = "$A_SUM" ] && [ "$(sum "$H/vault-stacks/alpha.md")" = "$C_SUM" ] \
    || fail "check wrote a file"
run write "$H" >/dev/null 2>&1 || fail "write after the edit"
run check "$H" >/dev/null 2>&1 || fail "check not clean after a write"
ok "check reports alpha's copy and the block stale after a page edit, writes nothing, and a write clears it"

# --- 10. the home resolver: argument, else $CODEX_HOME, else ~/.codex --------
python3 - <<'EOF' || fail "home resolver"
import os, sys
sys.path.insert(0, os.environ["LIB"])
import stack_target_codex as T
home = os.environ["HOME"]
assert T.resolve_codex_home("/x/arg") == "/x/arg"
os.environ["CODEX_HOME"] = "/x/env"
assert T.resolve_codex_home(None) == "/x/env"
assert T.resolve_codex_home("~/c") == os.path.join(home, "c")
del os.environ["CODEX_HOME"]
assert T.resolve_codex_home(None) == os.path.join(home, ".codex")
EOF
ok "the Codex home is the argument, else \$CODEX_HOME, else ~/.codex"

echo "PASS: test_vault_context_target_codex.sh"
