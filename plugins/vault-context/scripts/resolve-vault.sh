#!/usr/bin/env bash
# resolve-vault.sh — resolve the Obsidian vault path for both obsidian-wiki and
# vault-context plugins. This script is mirrored byte-for-byte into both plugins so
# neither has to import from the other.
#
# Resolution order:
#   1. $OBSIDIAN_VAULT_PATH env var (per-shell override)
#   2. ~/.config/obsidian-wiki/config.json `default_vault` field
#   3. Hard fallback: ~/dev/knowledge
#
# Output:
#   - On success: prints the absolute resolved vault path to stdout, exits 0.
#   - On failure: prints an error to stderr, exits 1.
#
# A path "resolves" only if it exists and is a directory. The fallback is tried last
# and may itself not exist; in that case the script exits non-zero so callers can
# decide whether to prompt the user.

set -euo pipefail

expand_tilde() {
    # POSIX-ish tilde expansion that doesn't require bash 4+
    local p="$1"
    case "$p" in
        "~")     printf '%s\n' "$HOME" ;;
        "~/"*)   printf '%s\n' "$HOME/${p#~/}" ;;
        *)       printf '%s\n' "$p" ;;
    esac
}

try_path() {
    local raw="$1"
    [ -z "$raw" ] && return 1
    local expanded
    expanded="$(expand_tilde "$raw")"
    if [ -d "$expanded" ]; then
        # realpath for stable canonical output; fall back to expanded if unavailable
        if command -v realpath >/dev/null 2>&1; then
            realpath "$expanded"
        else
            printf '%s\n' "$expanded"
        fi
        return 0
    fi
    return 1
}

# 1. Env var override
if [ -n "${OBSIDIAN_VAULT_PATH:-}" ]; then
    if try_path "$OBSIDIAN_VAULT_PATH"; then
        exit 0
    fi
    # Env var was set but does not point to a real directory: that's an error,
    # not a silent fallthrough. The user explicitly told us where the vault is.
    printf 'resolve-vault: OBSIDIAN_VAULT_PATH=%s does not exist or is not a directory\n' \
        "$OBSIDIAN_VAULT_PATH" >&2
    exit 1
fi

# 2. Config file
config_file="$HOME/.config/obsidian-wiki/config.json"
if [ -f "$config_file" ]; then
    # Parse with python3 stdlib only — no jq dependency. Empty output if the field
    # is missing or the JSON is invalid; we then fall through to step 3.
    config_path="$(python3 - "$config_file" <<'PY' 2>/dev/null || true
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
    p = data.get("default_vault", "")
    if isinstance(p, str):
        print(p)
except Exception:
    pass
PY
)"
    if [ -n "$config_path" ]; then
        if try_path "$config_path"; then
            exit 0
        fi
    fi
fi

# 3. Hard fallback
if try_path "~/dev/knowledge"; then
    exit 0
fi

printf 'resolve-vault: no vault found (tried OBSIDIAN_VAULT_PATH, %s, ~/dev/knowledge)\n' \
    "$config_file" >&2
exit 1
