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
#   stack-rule-foreign   (error) a vault-stack-*.md (or .mdc) the tool did not write
#
# For the other two hosts, only when the owner uses them here:
#   stack-cursor-rule-stale  (warn)  this project's Cursor rule is missing, differs from
#                                    its page, or its stack no longer applies — checked
#                                    when the project's .cursor/rules/ (at its git top
#                                    level) already holds a generated vault-stack-*.mdc
#   stack-cursor-refused     (warn)  git would commit this project's Cursor rules
#   stack-codex-copy-stale   (warn)  a Codex copy is missing, stale or orphaned
#   stack-codex-block-stale  (warn)  the pointer block in the Codex AGENTS file is
#                                    missing, stale, misplaced or left over
#   stack-codex-refused      (error) the Codex AGENTS file or copies folder holds a shape
#                                    the sync refuses (a broken marker pair, an
#                                    unmarked copy); both checked when
#                                    ${CODEX_HOME:-~/.codex}/vault-stacks/ exists
#
# Activates only when the vault resolves and holds Portfolio/stacks/; anywhere else
# (CI, a machine without the vault) the lane is clean. Claude Code's copies and the
# Codex home are user-level, so for them the project root is the report's target,
# not a filter; the Cursor check reads this project's rules.
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


# --- Codex: only when its copies folder exists ----------------------------------
codex_home="${CODEX_HOME:-$HOME/.codex}"
if [ -d "$codex_home/vault-stacks" ]; then
  cout="$(python3 "$DIR/sync-stack-rules.py" --vault "$vault" --host codex --check --json 2>"$errf" || true)"
  if printf '%s' "$cout" | jq -e '.codex' >/dev/null 2>&1; then
    while IFS=$'\t' read -r sev rule path msg; do
      [ -n "$rule" ] || continue
      add_finding "$sev" "$rule" stacks "$path" 0 "$msg"
    done < <(printf '%s' "$cout" | jq -r --arg fix "$FIX" '
      ( (.codex.findings // [])[]
          | ["warn", .code, .path,
             (if .slug then "Codex copy of stack \(.slug) is \(.state) — \($fix) --host codex"
              else "the stack pointer block in \(.path) is \(.state) — \($fix) --host codex" end)] ),
      ( (.codex.refused // [])[]
          | ["error","stack-codex-refused",.path,"the sync refuses this Codex file: \(.reason)"] )
      | map(gsub("[\t\n]"; " ")) | @tsv')
  else
    add_finding error stack-sync-error stacks "scripts/sync-stack-rules.py" 0 \
      "sync-stack-rules.py --host codex --check --json produced no valid JSON: $(tail -c 300 "$errf" | tr '\n' ' ')"
  fi
fi

# --- Cursor: only when this project already holds a generated rule --------------
top="$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null || printf '%s' "$ROOT")"
if compgen -G "$top/.cursor/rules/vault-stack-*.mdc" >/dev/null; then
  kout="$(python3 "$DIR/sync-stack-rules.py" --vault "$vault" --host cursor --project "$ROOT" --check --json 2>"$errf" || true)"
  if printf '%s' "$kout" | jq -e '.cursor' >/dev/null 2>&1; then
    while IFS=$'\t' read -r sev rule path msg; do
      [ -n "$rule" ] || continue
      add_finding "$sev" "$rule" stacks "$path" 0 "$msg"
    done < <(printf '%s' "$kout" | jq -r --arg fix "$FIX" '
      .cursor[] |
      ( ((.drift // [])[]
          | ["warn","stack-cursor-rule-stale",.rule,"Cursor rule for stack \(.slug) is \(.state) — \($fix) --host cursor --project <this project>"] ),
        ((.foreign // [])[]
          | ["error","stack-rule-foreign",.,"named like a generated stack rule but has no vault-context marker; the sync leaves it alone and stops — rename or remove it"] ),
        (select(.status == "refused" and ((.foreign // []) | length) == 0)
          | ["warn","stack-cursor-refused",(.rules_dir // .project),(.messages | join("; "))] ) )
      | map(gsub("[\t\n]"; " ")) | @tsv')
  else
    add_finding error stack-sync-error stacks "scripts/sync-stack-rules.py" 0 \
      "sync-stack-rules.py --host cursor --check --json produced no valid JSON: $(tail -c 300 "$errf" | tr '\n' ' ')"
  fi
fi

render_findings "validate-stacks.sh" "$ROOT"; exit $?
