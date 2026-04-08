#!/usr/bin/env bash
# session-start.sh — SessionStart hook for vault-context.
#
# Prints a one-line prompt to stdout (which Claude Code surfaces as a session message)
# the first time the user enters a fresh project that doesn't yet have a
# .claude/vault-context.md sidecar. Exits silently in any other case.
#
# Five gates (all must pass):
#   1. Vault is configured (resolve-vault.sh exits 0)
#   2. <vault>/index.md exists
#   3. cwd is inside a git repo
#   4. cwd is NOT itself under the vault path (avoid circular linking)
#   5. <cwd>/.claude/vault-context.md does NOT already exist
#
# This script never modifies a file. The user has to opt in by running
# /vault-context:link.

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

# Gate 5: sidecar does not yet exist
[ -e "$PWD/.claude/vault-context.md" ] && exit 0

# All gates passed: emit the prompt as a JSON systemMessage. Plain-text stdout
# from a SessionStart hook only reaches the model's additionalContext — it is
# never rendered in the user's TUI. Only `{"systemMessage": "..."}` JSON is
# surfaced as a visible "SessionStart:startup says: …" gray line.
msg='[vault-context] No vault context for this project yet. Run `/vault-context:link` to scan your vault and surface relevant pages.'
printf '{"systemMessage":"%s"}\n' "$msg"
