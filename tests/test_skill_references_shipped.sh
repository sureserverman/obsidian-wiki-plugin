#!/usr/bin/env bash
# test_skill_references_shipped.sh — every reference file a SKILL.md tells the
# agent to read must exist AND be tracked by git.
#
# Regression: scan-sessions/references/storage-paths.md was present in the
# working tree but listed in .gitignore (commit bf8e0bb), so it was absent from
# every clone, every marketplace copy and every installed version from 0.5.0 to
# 0.7.0 — while SKILL.md still opened with "Read references/storage-paths.md ...
# Trust it over your own assumptions about paths." Existing-on-disk is not the
# check; shipped is.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

git rev-parse --git-dir >/dev/null 2>&1 || {
    echo "  skip: not a git checkout, cannot verify tracking"
    echo "ALL OK"
    exit 0
}

CHECKED=0
PROBLEMS=0

while IFS= read -r skill; do
    skill_dir="$(dirname "$skill")"
    # Citations look like `references/foo.md` or `../other-skill/references/foo.md`
    while IFS= read -r ref; do
        [ -n "$ref" ] || continue
        # Resolve relative to the citing SKILL.md, then back to a repo path.
        target="$(cd "$skill_dir" 2>/dev/null && realpath -m --relative-to="$ROOT" "$ref" 2>/dev/null)"
        [ -n "$target" ] || continue
        CHECKED=$((CHECKED + 1))

        if [ ! -f "$ROOT/$target" ]; then
            echo "  MISSING: $target (cited by ${skill#./})" >&2
            PROBLEMS=$((PROBLEMS + 1))
            continue
        fi
        if ! git ls-files --error-unmatch "$target" >/dev/null 2>&1; then
            reason="$(git check-ignore -v "$target" 2>/dev/null)"
            echo "  UNTRACKED: $target (cited by ${skill#./})" >&2
            [ -n "$reason" ] && echo "             ignored by: $reason" >&2
            PROBLEMS=$((PROBLEMS + 1))
        fi
    done < <(grep -oE '(\.\./[a-z0-9-]+/)?references/[A-Za-z0-9._-]+\.md' "$skill" | sort -u)
done < <(find plugins -type f -name 'SKILL.md' | sort)

[ "$CHECKED" -gt 0 ] || fail "no reference citations found — did the grep pattern rot?"
[ "$PROBLEMS" -eq 0 ] || fail "$PROBLEMS cited reference file(s) missing or untracked"
ok "all $CHECKED cited reference file(s) exist and are git-tracked"

# Guard the specific file the regression removed, by name, so a future blanket
# ignore rule fails loudly here rather than silently at install time.
STORAGE_PATHS="plugins/obsidian-wiki/skills/scan-sessions/references/storage-paths.md"
[ -f "$STORAGE_PATHS" ] || fail "$STORAGE_PATHS is gone"
git ls-files --error-unmatch "$STORAGE_PATHS" >/dev/null 2>&1 \
    || fail "$STORAGE_PATHS is not tracked — it will not ship (check .gitignore)"
ok "storage-paths.md is tracked and will ship"

echo "ALL OK"
