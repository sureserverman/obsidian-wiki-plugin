#!/usr/bin/env bash
# validate-link.sh <project-root> [--json]
# Deterministic checks on a project's vault-context LINK STATE: the
# .claude/vault-context.md sidecar, its CLAUDE.md @-import block, and their
# mutual consistency and freshness. This is the mechanical half of /status and
# the safety guards in the /link skill, expressed once. The user-facing report
# wording and the decision to refresh stay with the commands.
set -eu
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/lib/findings.sh"
. "$DIR/lib/eligibility.sh"
have_jq

JSON=0; ARGS=()
for a in "$@"; do case "$a" in --json) JSON=1 ;; *) ARGS+=("$a") ;; esac; done
[ "$JSON" = 1 ] && export FINDINGS_JSON=1
ROOT="${ARGS[0]:-.}"
# `pwd -P`, not `pwd`: the write path canonicalizes physically (write-context.sh),
# and both feed the same string to project_eligible, which compares registry paths
# literally. A logical path would make the two callers reach opposite verdicts on
# the identical directory whenever it is reached through a symlink — the exact
# drift lib/eligibility.sh exists to prevent.
ROOT="$(cd "$ROOT" 2>/dev/null && pwd -P || true)"
[ -n "$ROOT" ] && [ -d "$ROOT" ] || { echo "usage: $0 <project-root> [--json]" >&2; exit 2; }

SIDECAR="$ROOT/.claude/vault-context.md"
CLAUDEMD="$ROOT/CLAUDE.md"

# Does CLAUDE.md carry the import block? (start+end markers, between them the
# @-import line written by /link.)
has_import=0
if [ -f "$CLAUDEMD" ] && grep -q '<!-- vault-context:start -->' "$CLAUDEMD" 2>/dev/null; then
  has_import=1
fi

# Activate only when this project has link state — a sidecar or an import block.
# An unlinked project (or the plugin root, the structural gate's target) has
# neither, so the lane is trivially clean there.
if [ ! -f "$SIDECAR" ] && [ "$has_import" -eq 0 ]; then
  render_findings "validate-link.sh" "$ROOT"; exit $?
fi

# --- circular link guard -----------------------------------------------------
# /link refuses to run with cwd at or under the vault; a sidecar there is wrong.
# Resolve via this plugin's own resolver; skip the check if no vault is set up.
vault="$(bash "$DIR/resolve-vault.sh" 2>/dev/null || true)"
if [ -n "$vault" ]; then
  vault_real="$(cd "$vault" 2>/dev/null && pwd -P || true)"
  # $ROOT is already physical (see above), so no second resolution is needed.
  root_real="$ROOT"
  if [ -n "$vault_real" ] && { [ "$root_real" = "$vault_real" ] || case "$root_real/" in "$vault_real"/*) true ;; *) false ;; esac; }; then
    add_finding error link-circular link ".claude/vault-context.md" 0 \
      "project root is at or under the vault ($vault_real) — vault-context must not link the vault to itself"
  fi
fi

# --- area-directory guard ----------------------------------------------------
# The write path (write-context.sh) refuses these outright; this is the
# deterministic backstop for a sidecar written before the guard existed, or by
# hand. Same rule, one definition: scripts/lib/eligibility.sh.
if ! project_eligible "$ROOT"; then
  add_finding error link-area-directory link ".claude/vault-context.md" 0 \
    "project root is an area directory, not a project — it is not a git repo, and is either absent from $VAULT_CONTEXT_REGISTRY or holds other registered projects beneath it; remove the sidecar and its CLAUDE.md import block with /vault-context:unlink and link the child projects instead"
fi

# --- sidecar well-formedness -------------------------------------------------
if [ -f "$SIDECAR" ]; then
  grep -q '<!-- vault-context:body:start -->' "$SIDECAR" 2>/dev/null && \
  grep -q '<!-- vault-context:body:end -->' "$SIDECAR" 2>/dev/null || \
    add_finding warn link-sidecar-no-body-markers link ".claude/vault-context.md" 0 \
      "sidecar is missing the <!-- vault-context:body:start/end --> markers — regenerate with /vault-context:refresh"
  grep -q '^Vault:' "$SIDECAR" 2>/dev/null || \
    add_finding warn link-sidecar-no-header link ".claude/vault-context.md" 0 \
      "sidecar is missing its 'Vault: … | Index: …' header line — regenerate with /vault-context:refresh"
fi

# --- import/sidecar drift ----------------------------------------------------
if [ -f "$SIDECAR" ] && [ "$has_import" -eq 0 ]; then
  add_finding warn link-import-missing link "CLAUDE.md" 0 \
    "sidecar exists but CLAUDE.md has no '<!-- vault-context:start -->' @-import block — fix with /vault-context:link --force"
fi
if [ ! -f "$SIDECAR" ] && [ "$has_import" -eq 1 ]; then
  add_finding warn link-import-dangling link "CLAUDE.md" 0 \
    "CLAUDE.md imports .claude/vault-context.md but the sidecar does not exist — run /vault-context:link or remove the block with /vault-context:unlink"
fi
if [ "$has_import" -eq 1 ] && [ -f "$CLAUDEMD" ]; then
  grep -q '@.claude/vault-context.md' "$CLAUDEMD" 2>/dev/null || \
    add_finding warn link-import-no-ref link "CLAUDE.md" 0 \
      "vault-context markers are present but do not contain the '@.claude/vault-context.md' import line"
fi

# --- freshness (nudges) ------------------------------------------------------
if [ -f "$SIDECAR" ] && [ -n "$vault" ] && [ -f "$vault/index.md" ]; then
  mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0; }
  s_m="$(mtime "$SIDECAR")"; i_m="$(mtime "$vault/index.md")"
  if [ "$i_m" -gt "$s_m" ] 2>/dev/null; then
    add_finding info link-sidecar-stale link ".claude/vault-context.md" 0 \
      "vault index is newer than this sidecar — refresh with /vault-context:refresh"
  fi
  if find "$vault/index.md" -mtime +30 -print 2>/dev/null | grep -q .; then
    add_finding info link-index-stale link ".claude/vault-context.md" 0 \
      "vault index.md is over 30 days old — consider re-running /obsidian-wiki:index from the vault"
  fi
fi

render_findings "validate-link.sh" "$ROOT"; exit $?
