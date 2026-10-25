#!/usr/bin/env bash
# install.sh — copy a Cursor port into Cursor's local plugin root.
#
#   bash ports/cursor/install.sh                  # sync ports/cursor/obsidian-wiki -> ~/.cursor/plugins/local/obsidian-wiki
#   bash ports/cursor/install.sh vault-portfolio  # sync ports/cursor/vault-portfolio -> ~/.cursor/plugins/local/vault-portfolio
#   bash ports/cursor/install.sh --dry-run        # show what rsync would do (with either name)
#
# One optional plugin name: obsidian-wiki (the default) or vault-portfolio. Any
# other name exits 2. Whole-directory sync with --delete, so a re-port removes
# files the port no longer ships. Refuses a symlinked target: an earlier-era
# symlink would make --delete act on the source tree. Nothing here touches
# ~/.cursor/hooks.json, ~/.cursor/skills, or any other plugin — neither port
# has hooks, by design. CURSOR_PLUGIN_LOCAL_ROOT overrides the local root.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

dry=""
name=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) dry="--dry-run" ;;
        -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
        obsidian-wiki|vault-portfolio)
            if [ -n "$name" ]; then
                echo "install.sh: one plugin name only, got $name and $arg" >&2
                exit 2
            fi
            name="$arg" ;;
        -*) echo "install.sh: unknown argument: $arg" >&2; exit 2 ;;
        *) echo "install.sh: unknown argument: $arg (the plugin name is obsidian-wiki or vault-portfolio)" >&2; exit 2 ;;
    esac
done
name="${name:-obsidian-wiki}"
src="$here/$name"
dest="${CURSOR_PLUGIN_LOCAL_ROOT:-$HOME/.cursor/plugins/local}/$name"

[ -d "$src" ] || { echo "install.sh: $src not found (run from the repo, or fix the path)" >&2; exit 1; }
[ -d "$src/.cursor-plugin" ] || { echo "install.sh: $src is not a Cursor plugin dir (no .cursor-plugin/)" >&2; exit 1; }
command -v rsync >/dev/null 2>&1 || { echo "install.sh: rsync is required" >&2; exit 1; }
if [ -L "$dest" ]; then
    echo "install.sh: refusing: $dest is a symlink; remove it and re-run" >&2
    exit 1
fi

mkdir -p "$(dirname "$dest")"
rsync -a --delete ${dry:+"$dry"} --exclude '__pycache__' "$src/" "$dest/"
echo "$name Cursor port -> $dest${dry:+ (dry run)}"
