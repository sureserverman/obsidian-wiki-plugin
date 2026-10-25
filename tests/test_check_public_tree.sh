#!/usr/bin/env bash
# check-public-tree.py: a tracked file naming a real home or mount path fails the
# check; a documented placeholder passes; an unreadable file is refused (exit 2).
set -uo pipefail
cd "$(dirname "$0")/.."
CHECK="$PWD/scripts/check-public-tree.py"
TMP="$(mktemp -d)"; trap 'chmod -R u+r "$TMP" 2>/dev/null; rm -rf "$TMP"' EXIT
fail=0
ok(){ printf '  ok    %s\n' "$1"; }
bad(){ printf '  FAIL  %s\n' "$1"; fail=1; }
repo(){ rm -rf "$TMP/r"; git init -q "$TMP/r"; printf '%s\n' "$1" > "$TMP/r/a.md"; git -C "$TMP/r" add a.md; }

# Planted paths are built at run time, so this tracked file never holds one.
H=/home; M=/mnt
repo "see $H/carol/dev/x"
python3 "$CHECK" --root "$TMP/r" >/dev/null 2>&1; [ $? -eq 1 ] && ok "a real home path fails" || bad "a real home path passed"
repo "notes live in $M/vault/Portfolio"
python3 "$CHECK" --root "$TMP/r" >/dev/null 2>&1; [ $? -eq 1 ] && ok "a real mount path fails" || bad "a real mount path passed"
E=home
repo "transcripts in ~/.claude/projects/-$E-carol-dev-x/"
python3 "$CHECK" --root "$TMP/r" >/dev/null 2>&1; [ $? -eq 1 ] && ok "an encoded Claude project folder fails" || bad "an encoded Claude project folder passed"
repo "cursor keeps ~/.cursor/projects/$E-carol-dev-x/"
python3 "$CHECK" --root "$TMP/r" >/dev/null 2>&1; [ $? -eq 1 ] && ok "an encoded Cursor project folder fails" || bad "an encoded Cursor project folder passed"
repo "e.g. -$E-alice-dev-foo and $E-alice-dev-foo"
python3 "$CHECK" --root "$TMP/r" >/dev/null 2>&1; [ $? -eq 0 ] && ok "encoded placeholders pass" || bad "an encoded placeholder failed"
repo 'e.g. /home/alice/dev/foo and /Users/someone/x and /mnt/notes'
python3 "$CHECK" --root "$TMP/r" >/dev/null 2>&1; [ $? -eq 0 ] && ok "placeholders pass" || bad "a placeholder failed"
repo 'clean'; mkdir "$TMP/r/d"; ln -s d "$TMP/r/link"; ln -s gone "$TMP/r/dangling"; git -C "$TMP/r" add link dangling
python3 "$CHECK" --root "$TMP/r" >/dev/null 2>&1; [ $? -eq 0 ] && ok "tracked symlinks (to a dir, dangling) are skipped" || bad "a tracked symlink broke the check"
repo 'clean'; chmod 000 "$TMP/r/a.md"
if [ "$(id -u)" -ne 0 ]; then
  python3 "$CHECK" --root "$TMP/r" >/dev/null 2>&1; [ $? -eq 2 ] && ok "an unreadable file is refused (exit 2)" || bad "an unreadable file was not refused"
fi
python3 "$CHECK" >/dev/null 2>&1 && ok "this repo's tree passes" || bad "this repo's tree fails"
exit $fail
