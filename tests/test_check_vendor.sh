#!/usr/bin/env bash
# test_check_vendor.sh — scripts/check-vendor.py catches a vendored file that
# drifted from its lock, in either direction, and --write re-vendors it.
#
# vault-portfolio carries a copy of the planning plugin's plan parser under
# src/vault-portfolio/core/vendor/, pinned by vendor.lock (`<file> <sha256>
# <upstream commit>` per line). Everything here runs on throwaway copies: a temp
# upstream git repo standing in for the planning repo, and a temp tree holding
# a copy of the checker, so neither the real upstream nor this repo is touched.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHECKER="$ROOT/scripts/check-vendor.py"

FAILS=0
fail() { echo "FAIL: $*" >&2; FAILS=$((FAILS + 1)); }
ok()   { echo "  ok: $*"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

UP="$WORK/upstream"
TREE="$WORK/tree"
VEN="$TREE/src/vault-portfolio/core/vendor"
LOCK="$VEN/vendor.lock"

# No hooks: a machine's init template may install a pre-commit hook that edits
# .gitignore and aborts the commit, which would leave the temp repo unborn.
gitq() { git -C "$UP" -c core.hooksPath=/dev/null -c user.name=t \
    -c user.email=t@example.invalid "$@" >/dev/null; }

mkdir -p "$UP/core/lib" "$TREE/scripts" "$VEN/staged_planning"
printf 'STATUS = "one"\n' > "$UP/core/lib/plan_parser.py"
git -C "$UP" init -q --template= && gitq add -A && gitq commit -q -m one
cp "$CHECKER" "$TREE/scripts/check-vendor.py"
cp "$UP/core/lib/plan_parser.py" "$VEN/staged_planning/plan_parser.py"
sum() { sha256sum "$1" | cut -d' ' -f1; }
printf 'plan_parser.py %s %s\n' "$(sum "$UP/core/lib/plan_parser.py")" \
    "$(git -C "$UP" rev-parse HEAD)" > "$LOCK"

run() { python3 "$TREE/scripts/check-vendor.py" --upstream "$UP" "$@" >/dev/null 2>&1; }

run && ok "an untouched vendored copy passes" || fail "a clean vendored copy failed"

# --- a one-byte edit of the vendored copy -------------------------------------
cp "$VEN/staged_planning/plan_parser.py" "$WORK/keep.py"
printf '#' >> "$VEN/staged_planning/plan_parser.py"
run; rc=$?
[ "$rc" -eq 1 ] && ok "an edited vendored copy fails (exit 1)" \
    || fail "an edited vendored copy: exit $rc, want 1"
cp "$WORK/keep.py" "$VEN/staged_planning/plan_parser.py"

# --- a file in the vendored package that the lock does not name ---------------
printf 'x = 1\n' > "$VEN/staged_planning/extra.py"
run; rc=$?
[ "$rc" -eq 1 ] && ok "an unlocked vendored file fails (exit 1)" \
    || fail "an unlocked vendored file: exit $rc, want 1"
rm -f "$VEN/staged_planning/extra.py"

# --- a lock line this tool cannot parse ---------------------------------------
cp "$LOCK" "$WORK/keep.lock"
printf 'plan_parser.py nothex\n' > "$LOCK"
run; rc=$?
[ "$rc" -eq 2 ] && ok "a malformed lock line is refused (exit 2)" \
    || fail "a malformed lock line: exit $rc, want 2"
cp "$WORK/keep.lock" "$LOCK"

# --- an upstream that is not a git repo is a usage error ----------------------
mkdir -p "$WORK/plain/core/lib"; cp "$UP/core/lib/plan_parser.py" "$WORK/plain/core/lib/"
python3 "$TREE/scripts/check-vendor.py" --upstream "$WORK/plain" >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] && ok "a non-git upstream is refused (exit 2)" \
    || fail "a non-git upstream: exit $rc, want 2"

# --- upstream HEAD moved on while its working tree still shows the locked bytes -
cp "$UP/core/lib/plan_parser.py" "$WORK/locked.py"
printf '#' >> "$UP/core/lib/plan_parser.py"; gitq commit -q -am ahead
cp "$WORK/locked.py" "$UP/core/lib/plan_parser.py"
run; rc=$?
[ "$rc" -eq 1 ] && ok "an upstream HEAD that differs from the lock fails, whatever the working tree shows" \
    || fail "upstream HEAD ahead of the lock: exit $rc, want 1"
gitq checkout -q HEAD~1 -- core/lib/plan_parser.py; gitq commit -q -m back

# --- a one-byte edit of the upstream copy, committed --------------------------
printf '#' >> "$UP/core/lib/plan_parser.py"
gitq commit -q -am two
run; rc=$?
[ "$rc" -eq 1 ] && ok "an upstream change fails the check (exit 1)" \
    || fail "an upstream change: exit $rc, want 1"

# --- --write refuses an upstream file with uncommitted changes ----------------
printf '#' >> "$UP/core/lib/plan_parser.py"
run --write; rc=$?
[ "$rc" -ne 0 ] && cmp -s "$WORK/keep.lock" "$LOCK" \
    && ok "--write refuses a dirty upstream file and leaves the lock alone" \
    || fail "--write on a dirty upstream file: exit $rc, or the lock changed"
git -C "$UP" checkout -q -- core/lib/plan_parser.py

# --- --write re-vendors, and records the upstream commit ----------------------
run --write; rc=$?
head2="$(git -C "$UP" rev-parse HEAD)"
if [ "$rc" -eq 0 ] && run && grep -q " $head2\$" "$LOCK" \
    && cmp -s "$UP/core/lib/plan_parser.py" "$VEN/staged_planning/plan_parser.py"; then
    ok "--write re-copies the file, records the new commit, and the check passes"
else
    fail "--write: exit $rc; lock is: $(cat "$LOCK")"
fi

# --- a lock commit whose copy of the file is not the locked one ---------------
sed -i "s/ $head2\$/ $(git -C "$UP" rev-parse HEAD~1)/" "$LOCK"
run; rc=$?
[ "$rc" -eq 1 ] && ok "a lock commit that does not hold the locked bytes fails (exit 1)" \
    || fail "a wrong lock commit: exit $rc, want 1"

[ "$FAILS" -eq 0 ] || { echo "$FAILS failure(s)" >&2; exit 1; }
echo "ALL OK"
