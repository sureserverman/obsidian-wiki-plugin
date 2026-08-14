#!/usr/bin/env bash
# publish-vault-path.sh — SessionStart hook: resolve the vault once and write
# the answer where skills can Read it.
#
# Why this exists
# ---------------
# Every skill needs the vault path, and until 0.9.0 each one got it by running
# `bash "$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh"`. That forced a
# `Bash(bash:*)` entry in twelve skills' allowed-tools — a grant that restricts
# nothing, because bash is an interpreter and `bash -c '<anything>'` matches the
# same prefix. The 2026-08-13 sec-audit run rated it HIGH (CWE-693) on every
# skill that parses untrusted session transcripts.
#
# Scoping that grant tighter is not possible: a permission pattern cannot name
# ${CLAUDE_PLUGIN_ROOT}/scripts/resolve-vault.sh, whose absolute path differs
# per install. So the dependency is removed instead of narrowed.
#
# Hooks are not governed by `allowed-tools` — they are scripts the host runs
# directly — so resolution keeps happening in exactly one place, with the same
# precedence as before ($OBSIDIAN_VAULT_PATH first). Skills read the result.
# That preserves the env-var override, which a skill reading config.json
# directly would have silently ignored: hooks would write to one vault while
# skills read another.
#
# Writes ONE file:
#   <config>/obsidian-wiki/state/vault-path   the resolved absolute path
#
# Silent exit conditions (leave any previous value in place rather than
# replacing a good answer with a guess):
#   - $OBSIDIAN_WIKI_NO_PUBLISH_VAULT is set (kill switch)
#   - resolve-vault.sh is missing or resolves nothing

set -u  # not -e — a hook must never crash the host session

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
resolve_vault="$script_dir/resolve-vault.sh"

# Read (and discard) hook stdin so a piped payload cannot accumulate.
cat >/dev/null 2>&1 || true

[ -n "${OBSIDIAN_WIKI_NO_PUBLISH_VAULT:-}" ] && exit 0
[ -f "$resolve_vault" ] || exit 0

vault_path="$(bash "$resolve_vault" 2>/dev/null)" || exit 0
[ -n "$vault_path" ] || exit 0
[ -d "$vault_path" ] || exit 0

state_dir="${XDG_CONFIG_HOME:-$HOME/.config}/obsidian-wiki/state"
mkdir -p "$state_dir" 2>/dev/null || exit 0

# Write atomically: a skill reading this file must never see a partial path.
# mktemp, not "$$": a PID is predictable, and writing a fixed-name temp file is
# the same class of hazard this plugin just moved its update cache out of /tmp to
# avoid. The directory is user-owned, so the risk is small — which is exactly why
# it would have been easy to leave.
tmp="$(mktemp "$state_dir/.vault-path.XXXXXX" 2>/dev/null)" || exit 0
printf '%s\n' "$vault_path" > "$tmp" 2>/dev/null || { rm -f "$tmp" 2>/dev/null; exit 0; }
mv "$tmp" "$state_dir/vault-path" 2>/dev/null || rm -f "$tmp" 2>/dev/null

exit 0
