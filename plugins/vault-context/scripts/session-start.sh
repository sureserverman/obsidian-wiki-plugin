#!/usr/bin/env bash
# session-start.sh — SessionStart hook for vault-context.
#
# Two paths through this script (only one nudge fires per session):
#
# A. NO sidecar yet — print the "no vault context yet, run /vault-context:link"
#    nudge. Original behavior.
#
# B. Sidecar exists but is older than the vault index — print the
#    "sidecar is stale, run /vault-context:refresh" nudge. NEW in v0.3:
#    distributes per-project refresh whenever the user opens a project
#    after the daily vault-index regen.
#
# Common gates (must pass for either path):
#   1. Vault is configured (resolve-vault.sh exits 0)
#   2. <vault>/index.md exists
#   3. cwd is inside a git repo
#   4. cwd is NOT itself under the vault path (avoid circular linking)
#
# Then per-path:
#   Path A — gate 5a: <cwd>/.claude/vault-context.md does NOT exist
#   Path B — gate 5b: <cwd>/.claude/vault-context.md exists AND is older
#                     than <vault>/index.md, AND $VAULT_CONTEXT_NO_STALENESS_NUDGE
#                     is not set.
#
# This script never modifies a file.

set -euo pipefail

# Resolve script directory so we can call our sibling resolve-vault.sh regardless
# of how Claude Code invokes hooks.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Gate 1: vault configured
vault="$("$script_dir/resolve-vault.sh" 2>/dev/null)" || exit 0
[ -n "$vault" ] || exit 0

# Gate 2: vault index exists
[ -f "$vault/index.md" ] || exit 0

# Gate 3: cwd in a git repo
git rev-parse --show-toplevel >/dev/null 2>&1 || exit 0

# Gate 4: cwd not under the vault
cwd_real="$(realpath "$PWD" 2>/dev/null || printf '%s' "$PWD")"
vault_real="$(realpath "$vault" 2>/dev/null || printf '%s' "$vault")"
case "$cwd_real" in
    "$vault_real"|"$vault_real"/*) exit 0 ;;
esac

sidecar="$PWD/.claude/vault-context.md"

# Path A — sidecar missing: emit the link nudge.
if [ ! -e "$sidecar" ]; then
    msg='[vault-context] No vault context for this project yet. Run `/vault-context:link` to scan your vault and surface relevant pages.'
    printf '{"systemMessage":"%s"}\n' "$msg"
    exit 0
fi

# Path B — sidecar exists. If the staleness-nudge kill switch is set, exit.
[ -n "${VAULT_CONTEXT_NO_STALENESS_NUDGE:-}" ] && exit 0

# Compare mtimes. If the sidecar is older than the vault index, nudge for refresh.
# stat -c %Y is GNU coreutils; -f %m is BSD/macOS.
sidecar_mtime="$(stat -c %Y "$sidecar" 2>/dev/null || stat -f %m "$sidecar" 2>/dev/null || printf 0)"
index_mtime="$(stat -c %Y "$vault/index.md" 2>/dev/null || stat -f %m "$vault/index.md" 2>/dev/null || printf 0)"

if [ "$sidecar_mtime" -lt "$index_mtime" ]; then
    msg='[vault-context] Sidecar is older than the vault index — run `/vault-context:refresh` to pick up new pages.'
    printf '{"systemMessage":"%s"}\n' "$msg"
fi
exit 0
