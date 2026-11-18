#!/usr/bin/env bash
# validate-stacks.sh <project-root> [--json]
# The stack-rules slice of the lane: are the generated Claude Code rules in step
# with the vault's stack pages? It holds no rule of its own. It runs
# `sync-stack-rules.py --check --lint --json` — the one definition of drift — and
# maps that JSON onto findings:
#
#   stack-rule-stale     (warn)  a rule differs from its page, or its page is gone
#   stack-rule-missing   (warn)  a page has never been synced
#   stack-rule-legacy    (warn)  a generated copy left in the Claude rules folder,
#                                which would load the page a second time
#   stack-source-missing (warn)  a page's `sources` names a path that no longer exists
#   stack-page-invalid   (error) a page the sync tool refuses to parse
#   stack-rule-foreign   (error) a vault-stack-*.md the tool did not write
#
# Activates only when the vault resolves and holds Portfolio/stacks/; anywhere else
# (CI, a machine without the vault) the lane is clean. Stack rules are user-level,
# so the project root is the report's target, not a filter.
set -eu
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/lib/findings.sh"
have_jq

JSON=0; ARGS=()
for a in "$@"; do case "$a" in --json) JSON=1 ;; *) ARGS+=("$a") ;; esac; done
[ "$JSON" = 1 ] && export FINDINGS_JSON=1
ROOT="${ARGS[0]:-.}"
ROOT="$(cd "$ROOT" 2>/dev/null && pwd -P || true)"
[ -n "$ROOT" ] && [ -d "$ROOT" ] || { echo "usage: $0 <project-root> [--json]" >&2; exit 2; }

vault="$(bash "$DIR/resolve-vault.sh" 2>/dev/null || true)"
if [ -z "$vault" ] || [ ! -d "$vault/Portfolio/stacks" ]; then
  render_findings "validate-stacks.sh" "$ROOT"; exit $?
fi

errf="$(mktemp)"; trap 'rm -f "$errf"' EXIT
out="$(python3 "$DIR/sync-stack-rules.py" --vault "$vault" --check --lint --json 2>"$errf" || true)"
if ! printf '%s' "$out" | jq -e '.pages' >/dev/null 2>&1; then
  add_finding error stack-sync-error stacks "scripts/sync-stack-rules.py" 0 \
    "sync-stack-rules.py --check --lint --json produced no valid JSON: $(tail -c 300 "$errf" | tr '\n' ' ')"
  render_findings "validate-stacks.sh" "$ROOT"; exit $?
fi

FIX="run /vault-context:sync-rules"
while IFS=$'\t' read -r sev rule path msg; do
  [ -n "$rule" ] || continue
  add_finding "$sev" "$rule" stacks "$path" 0 "$msg"
done < <(printf '%s' "$out" | jq -r --arg fix "$FIX" '
  ( .pages[] | select(.state=="stale")
      | ["warn","stack-rule-stale",.rule,"rule for stack \(.slug) differs from its page — \($fix)"] ),
  ( .pages[] | select(.state=="missing")
      | ["warn","stack-rule-missing",.rule,"stack \(.slug) has no rule yet — \($fix)"] ),
  ( .orphans[]
      | ["warn","stack-rule-stale",.rule,"the page for stack \(.slug) is gone — \($fix) to remove its rule"] ),
  ( (.legacy // [])[]
      | ["warn","stack-rule-legacy",.rule,"stack \(.slug) has a copy left in the Claude rules folder, which loads the page a second time — \($fix) to remove it"] ),
  ( .sources_missing[]
      | ["warn","stack-source-missing",.path,"stack \(.slug) names a source that no longer exists; re-check the page against its sources"] ),
  ( .errors[]
      | ["error","stack-page-invalid",.page,"stack page refused: \(.reason)"] ),
  ( .foreign[]
      | ["error","stack-rule-foreign",.,"named like a generated stack rule but has no vault-context marker; the sync leaves it alone and stops — rename or remove it"] )
  | map(gsub("[\t\n]"; " ")) | @tsv')

render_findings "validate-stacks.sh" "$ROOT"; exit $?
