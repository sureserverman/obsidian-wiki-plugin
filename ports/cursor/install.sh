#!/usr/bin/env bash
# install.sh — copy the Cursor port into Cursor's local plugin root.
#
#   bash ports/cursor/install.sh            # sync ports/cursor/obsidian-wiki -> ~/.cursor/plugins/local/obsidian-wiki
#   bash ports/cursor/install.sh --dry-run  # show what rsync would do
#
# Whole-directory sync with --delete, so a re-port removes files the port no
# longer ships. Refuses a symlinked target: an earlier-era symlink would make
# --delete act on the source tree. Nothing here touches ~/.cursor/hooks.json,
# ~/.cursor/skills, or any other plugin — this port has no hooks by design.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/obsidian-wiki"
dest="${CURSOR_PLUGIN_LOCAL_ROOT:-$HOME/.cursor/plugins/local}/obsidian-wiki"

dry=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) dry="--dry-run" ;;
        -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
        *) echo "install.sh: unknown argument: $arg" >&2; exit 2 ;;
    esac
done

[ -d "$src/.cursor-plugin" ] || { echo "install.sh: $src is not a Cursor plugin dir (no .cursor-plugin/)" >&2; exit 1; }
command -v rsync >/dev/null 2>&1 || { echo "install.sh: rsync is required" >&2; exit 1; }
if [ -L "$dest" ]; then
    echo "install.sh: refusing: $dest is a symlink; remove it and re-run" >&2
    exit 1
fi

mkdir -p "$(dirname "$dest")"
rsync -a --delete $dry --exclude '__pycache__' "$src/" "$dest/"
echo "obsidian-wiki Cursor port -> $dest${dry:+ (dry run)}"
