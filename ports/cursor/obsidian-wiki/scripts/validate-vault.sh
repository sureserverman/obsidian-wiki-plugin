#!/usr/bin/env bash
# validate-vault.sh <vault-root> [--json]
# Deterministic vault-health checks: missing frontmatter, broken wikilinks,
# orphan pages. This is the MECHANICAL half of the /lint skill — grep-and-match
# work that decides the same way every run. The JUDGMENT half (possible
# contradictions, possibly-stale claims) stays in the skill, which runs this and
# reports its findings before adding the heuristic layer.
set -eu
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/lib/findings.sh"
have_jq

JSON=0; ARGS=()
for a in "$@"; do case "$a" in --json) JSON=1 ;; *) ARGS+=("$a") ;; esac; done
[ "$JSON" = 1 ] && export FINDINGS_JSON=1
ROOT="${ARGS[0]:-.}"
ROOT="$(cd "$ROOT" 2>/dev/null && pwd || true)"
[ -n "$ROOT" ] && [ -d "$ROOT" ] || { echo "usage: $0 <vault-root> [--json]" >&2; exit 2; }

# Activate only on an actual vault, identified by index.md at the root (every
# vault has one; a plugin root or arbitrary dir does not). This lets
# `validate.sh <plugin-root>` (the structural gate) pass trivially green while
# `validate.sh <vault>` does the real work — one code path, no false findings.
[ -f "$ROOT/index.md" ] || { render_findings "validate-vault.sh" "$ROOT"; exit $?; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cd "$ROOT"

# Every wiki .md except the non-page trees build-index.py also excludes.
all_md="$tmp/all_md"
find . -type d \( -name raw -o -name .obsidian -o -name .git \) -prune -o \
       -type f -name '*.md' -print | sed 's|^\./||' | sort > "$all_md"

# Checkable wiki pages: nested at least one dir deep (excludes root-level
# Home.md/index.md/CLAUDE.md/log.md) and not the auto-generated Portfolio tree.
pages="$tmp/pages"
awk -F/ 'NF>=2 && $1!="Portfolio"' "$all_md" > "$pages"

# Known link targets: every page's basename (lowercased, no .md). Portfolio and
# root pages are valid link targets, so they stay in this set.
known="$tmp/known"
sed 's|.*/||; s|\.md$||' "$all_md" | tr '[:upper:]' '[:lower:]' | sort -u > "$known"

# Declared aliases (lowercased) are also valid link targets.
aliases="$tmp/aliases"
: > "$aliases"
while IFS= read -r f; do
  extract_frontmatter "$f" 2>/dev/null | awk '
    /^aliases:[[:space:]]*\[/ {
      l=$0; sub(/^aliases:[[:space:]]*\[/,"",l); sub(/\].*$/,"",l)
      n=split(l,a,","); for(i=1;i<=n;i++){t=a[i]; gsub(/^[[:space:]]*"?/,"",t); gsub(/"?[[:space:]]*$/,"",t); if(t!="")print t}
      next
    }
    /^aliases:[[:space:]]*$/ { inl=1; next }
    inl && /^[[:space:]]*-[[:space:]]+/ { t=$0; sub(/^[[:space:]]*-[[:space:]]+/,"",t); gsub(/^[[:space:]]*"?/,"",t); gsub(/"?[[:space:]]*$/,"",t); if(t!="")print t; next }
    inl && /^[^[:space:]#-]/ { inl=0 }
  ' || true
done < "$pages" | tr '[:upper:]' '[:lower:]' | sort -u > "$aliases"

valid_targets="$tmp/valid"
cat "$known" "$aliases" | sort -u > "$valid_targets"

# Extract every [[wikilink]] from the wiki pages as: page<TAB>line<TAB>target.
# Skip fenced code blocks and inline `code` spans, so bash `[[ -f ]]` tests and
# regex like `[[:space:]]` are not mistaken for wikilinks (the /lint skill flags
# this exact false-positive). Targets keep their original case (the #section and
# |alias suffixes are dropped) — needed for the path-style existence check below.
links="$tmp/links"
: > "$links"
while IFS= read -r f; do
  awk '
    /^[[:space:]]*(```|~~~)/ { infence = !infence; next }
    infence { next }
    {
      line = $0
      gsub(/`[^`]*`/, "", line)            # drop inline code spans
      while (match(line, /\[\[[^]]+\]\]/)) {
        tok = substr(line, RSTART + 2, RLENGTH - 4)
        sub(/#.*$/, "", tok); sub(/\\?\|.*$/, "", tok)   # drop #section and (\)|alias
        sub(/^[[:space:]]+/, "", tok); sub(/[[:space:]]+$/, "", tok)
        if (tok != "") print NR "\t" tok
        line = substr(line, RSTART + RLENGTH)
      }
    }
  ' "$f" | while IFS="$(printf '\t')" read -r ln tok; do
    printf '%s\t%s\t%s\n' "$f" "$ln" "$tok"
  done
done < "$pages" >> "$links"

# 1. Broken wikilinks. A path-style link (e.g. [[raw/sessions/foo]]) is valid if
#    the file exists under the vault. Otherwise the target must match a page
#    basename or a declared alias (case-insensitive) — note a title may itself
#    contain a slash (e.g. "Build for Mac CI/CD Pipeline"), so we test file
#    existence first and fall through to basename matching, not the reverse.
while IFS="$(printf '\t')" read -r f ln t; do
  [ -n "$t" ] || continue
  [ -e "$t" ] && continue
  [ -e "$t.md" ] && continue
  t_lc="$(printf '%s' "$t" | tr '[:upper:]' '[:lower:]')"
  grep -Fxq "$t_lc" "$valid_targets" || \
    add_finding warn vault-broken-wikilink vault "$f" "$ln" \
      "wikilink [[$t]] resolves to no page, alias, or file — fix the target, create the page, or remove the link"
done < "$links"

# 2. Missing / incomplete frontmatter — page must open with a --- block that
#    closes and carries at least a title:. Report-only; never auto-write.
while IFS= read -r f; do
  if ! has_closing_fence "$f"; then
    add_finding warn vault-missing-frontmatter vault "$f" 1 \
      "page has no closing frontmatter block (--- … ---); expected at least title:"
    continue
  fi
  [ -n "$(frontmatter_field "$f" title)" ] || \
    add_finding warn vault-frontmatter-no-title vault "$f" 1 \
      "frontmatter present but no title: field"
done < "$pages"

# 3. Orphan pages — no inbound [[link]] from any wiki page. Candidates, not
#    defects: an orphan may be a page the user is about to link from a WIP note.
inbound="$tmp/inbound"
cut -f3 "$links" | tr '[:upper:]' '[:lower:]' | sort -u > "$inbound"
while IFS= read -r f; do
  b="$(printf '%s' "$f" | sed 's|.*/||; s|\.md$||' | tr '[:upper:]' '[:lower:]')"
  grep -Fxq "$b" "$inbound" || \
    add_finding info vault-orphan-page vault "$f" 0 \
      "no other page links to [[$b]] — add a backlink from a related page or confirm it is intentional"
done < "$pages"

render_findings "validate-vault.sh" "$ROOT"; exit $?
