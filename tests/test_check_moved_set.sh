#!/usr/bin/env bash
# test_check_moved_set.sh — scripts/check-moved-set.py accounts for every member
# of the source portfolio layer exactly once, and --complete demands that every
# claimed destination exists.
#
# The source is a temp git repo shaped like the planning repo's portfolio,
# compass and decisions trees; the destination is a temp tree holding a copy of
# the checker and its two provenance files. Nothing here reads a real repo.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHECKER="$ROOT/scripts/check-moved-set.py"

FAILS=0
fail() { echo "FAIL: $*" >&2; FAILS=$((FAILS + 1)); }
ok()   { echo "  ok: $*"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

SRC="$WORK/source"
TREE="$WORK/tree"
VP="$TREE/src/vault-portfolio"
C="src/vault-portfolio/core"

# The source: two portfolio files, a fixture dir, one compass file, one decisions
# file that stays where it is. No hooks: an init template's pre-commit hook could
# abort the commit and leave the repo unborn.
mkdir -p "$SRC/core/skills/portfolio/scripts" "$SRC/core/skills/portfolio/tests/fixtures/x" \
    "$SRC/core/skills/compass" "$SRC/core/skills/decisions"
echo a > "$SRC/core/skills/portfolio/scripts/a.py"
echo t > "$SRC/core/skills/portfolio/tests/test-a.py"
echo f > "$SRC/core/skills/portfolio/tests/fixtures/x/one.md"
echo s > "$SRC/core/skills/compass/SKILL.md"
echo k > "$SRC/core/skills/decisions/SKILL.md"
git -C "$SRC" init -q --template=
git -C "$SRC" -c core.hooksPath=/dev/null -c user.name=t -c user.email=t@example.invalid \
    add -A >/dev/null
git -C "$SRC" -c core.hooksPath=/dev/null -c user.name=t -c user.email=t@example.invalid \
    commit -qm src >/dev/null
REV="$(git -C "$SRC" rev-parse HEAD)"

mkdir -p "$TREE/scripts" "$VP"
cp "$CHECKER" "$TREE/scripts/check-moved-set.py"
git -C "$TREE" init -q --template=
# place <path under TREE> — create a destination file and stage it: a destination
# counts as present only when git tracks it.
place() { mkdir -p "$TREE/$(dirname "$1")"; echo x > "$TREE/$1"; git -C "$TREE" add -- "$1"; }
write_sets() {
    cat > "$VP/moved-from.txt" <<EOF
# comment lines and blank lines are skipped

$C/skills/portfolio/scripts/a.py <- core/skills/portfolio/scripts/a.py
$C/skills/portfolio/tests/test-a.py <- core/skills/portfolio/tests/test-a.py
$C/skills/compass/SKILL.md <- core/skills/compass/SKILL.md
EOF
    cat > "$VP/not-moved.txt" <<EOF
core/skills/decisions/SKILL.md -> R:core/skills/decisions/SKILL.md
core/skills/portfolio/tests/fixtures/x/ -> replaced:$C/skills/portfolio/tests/fixtures/x
EOF
}
write_sets

run() { python3 "$TREE/scripts/check-moved-set.py" --source-repo "$SRC" --source-rev "$REV" "$@" \
    >/dev/null 2>&1; }

run && ok "every member claimed once, destinations pending: default mode passes" \
    || fail "a fully claimed set with pending destinations failed the default mode"
run --complete; rc=$?
[ "$rc" -eq 1 ] && ok "pending destinations fail --complete" \
    || fail "--complete with pending destinations: exit $rc, want 1"

# --only limits --complete to its filter: create the tests/ destination only.
place "$C/skills/portfolio/tests/test-a.py"
run --complete --only '/tests/test-'; rc=$?
[ "$rc" -eq 0 ] && ok "--only limits the completeness demand to its filter" \
    || fail "--complete --only '/tests/test-': exit $rc, want 0"
run --complete --only '/scripts/'; rc=$?
[ "$rc" -eq 1 ] && ok "--only still fails a pending path inside its filter" \
    || fail "--complete --only '/scripts/': exit $rc, want 1"

# The destinations land; one left untracked does not count as present.
place "$C/skills/portfolio/scripts/a.py"
place "$C/skills/portfolio/tests/fixtures/x/synthetic.md"
mkdir -p "$TREE/$C/skills/compass"; echo s > "$TREE/$C/skills/compass/SKILL.md"
run --complete; rc=$?
[ "$rc" -eq 1 ] && ok "an untracked destination does not count as present" \
    || fail "--complete with only an untracked destination missing: exit $rc, want 1"
git -C "$TREE" add -- "$C/skills/compass/SKILL.md"

# Every destination present, but the replaced: dir holds nothing tracked.
git -C "$TREE" rm -q --cached -- "$C/skills/portfolio/tests/fixtures/x/synthetic.md"
run --complete; rc=$?
[ "$rc" -eq 1 ] && ok "a replaced: dir with nothing tracked fails --complete" \
    || fail "--complete with an empty replaced: dir: exit $rc, want 1"
git -C "$TREE" add -- "$C/skills/portfolio/tests/fixtures/x/synthetic.md"
run --complete && ok "every destination present: --complete passes" \
    || fail "--complete with every destination present failed"

# An unclaimed member.
sed -i '/compass\/SKILL.md/d' "$VP/moved-from.txt"
run; rc=$?
[ "$rc" -eq 1 ] && ok "an unclaimed member fails" || fail "an unclaimed member: exit $rc, want 1"
write_sets

# A member claimed twice: moved and also kept.
echo "core/skills/portfolio/scripts/a.py -> dropped: twice" >> "$VP/not-moved.txt"
run; rc=$?
[ "$rc" -eq 1 ] && ok "a doubly claimed member fails" || fail "a double claim: exit $rc, want 1"
write_sets

# A claimed source path that is not a member at the revision.
echo "$C/skills/portfolio/scripts/b.py <- core/skills/portfolio/scripts/b.py" >> "$VP/moved-from.txt"
run; rc=$?
[ "$rc" -eq 1 ] && ok "a source path absent at the revision fails" \
    || fail "an absent source path: exit $rc, want 1"
write_sets

# Two moved lines sharing one destination.
echo "$C/skills/compass/SKILL.md <- core/skills/portfolio/scripts/a.py" >> "$VP/moved-from.txt"
sed -i '/^src.*scripts\/a.py <- /d' "$VP/moved-from.txt"
run; rc=$?
[ "$rc" -eq 1 ] && ok "two sources claiming one destination fail" \
    || fail "a shared destination: exit $rc, want 1"
write_sets

# An R: target present in the source working tree but not committed there.
echo u > "$SRC/core/skills/decisions/UNTRACKED.md"
sed -i 's|R:core/skills/decisions/SKILL.md|R:core/skills/decisions/UNTRACKED.md|' "$VP/not-moved.txt"
run; rc=$?
[ "$rc" -eq 1 ] && ok "an R: target the source repo does not commit fails" \
    || fail "an uncommitted R: target: exit $rc, want 1"
rm -f "$SRC/core/skills/decisions/UNTRACKED.md"
write_sets

# An R: target that does not exist in the source repo.
sed -i 's|R:core/skills/decisions/SKILL.md|R:core/skills/decisions/GONE.md|' "$VP/not-moved.txt"
run; rc=$?
[ "$rc" -eq 1 ] && ok "a missing R: target fails" || fail "a missing R: target: exit $rc, want 1"
write_sets

# A line this tool cannot parse is refused, never guessed at.
echo "core/skills/compass/SKILL.md => somewhere" >> "$VP/not-moved.txt"
run; rc=$?
[ "$rc" -eq 2 ] && ok "a malformed line is refused (exit 2)" \
    || fail "a malformed line: exit $rc, want 2"
write_sets

[ "$FAILS" -eq 0 ] || { echo "$FAILS failure(s)" >&2; exit 1; }
echo "ALL OK"
