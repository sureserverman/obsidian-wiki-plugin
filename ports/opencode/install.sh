#!/usr/bin/env bash
# install.sh — install the OpenCode port of vault-portfolio.
#
#   bash ports/opencode/install.sh            # sync ports/opencode/vault-portfolio -> <plugins>/vault-portfolio,
#                                             # copy its two commands into <config>/opencode/commands/,
#                                             # then print the opencode.json entries to add by hand
#   bash ports/opencode/install.sh --dry-run  # print the plan and the entries; write nothing
#
# <plugins> is $OPENCODE_PLUGIN_LOCAL_ROOT, else ${XDG_DATA_HOME:-~/.local/share}/opencode-plugins;
# <config> is ${XDG_CONFIG_HOME:-~/.config}. opencode.json is never edited: the skills path and
# the permission.external_directory entries are printed for the user to add. Nothing is written
# under ~/.claude or ~/.agents, whose skill folders OpenCode also reads; a target there is refused.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/vault-portfolio"
: "${HOME:?install.sh: HOME is not set}"
dest="${OPENCODE_PLUGIN_LOCAL_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/opencode-plugins}/vault-portfolio"
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
cmd_dir="$config_dir/commands"
commands=(vault-portfolio.md vault-compass.md)

dry=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) dry="--dry-run" ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "install.sh: unknown argument: $arg" >&2; exit 2 ;;
    esac
done

die() { echo "install.sh: $*" >&2; exit 1; }

[ -d "$src" ] || die "$src not found (build it first, or run from the repo)"
for f in skills/vault-portfolio/SKILL.md skills/vault-compass/SKILL.md "${commands[@]/#/commands/}"; do
    [ -f "$src/$f" ] || die "$src is not the OpenCode vault-portfolio port (no $f)"
done
command -v python3 >/dev/null 2>&1 || die "python3 is required"

# Refuse a target inside another tool's skill root: OpenCode lists ~/.claude/skills and
# ~/.agents/skills too, so a copy there would also reach Claude Code or other agents.
# Paths are compared resolved, so a symlinked parent cannot hide the real target.
python3 -I - "$HOME" "$dest" "$cmd_dir" <<'PY' || exit 1
import os, sys
home, targets = sys.argv[1], sys.argv[2:]
banned = [os.path.realpath(os.path.join(home, d)) for d in (".claude", ".agents")]
for t in targets:
    real = os.path.realpath(t)
    for b in banned:
        if real == b or real.startswith(b + os.sep):
            sys.exit(f"install.sh: refusing: {t} is under {b}, another tool's skill root")
PY
[ -L "$dest" ] && die "refusing: $dest is a symlink; remove it and re-run"
[ -e "$dest" ] && [ ! -d "$dest" ] && die "refusing: $dest exists and is not a directory"
for c in "${commands[@]}"; do
    [ -L "$cmd_dir/$c" ] && die "refusing: $cmd_dir/$c is a symlink; remove it and re-run"
    [ -e "$cmd_dir/$c" ] && [ ! -f "$cmd_dir/$c" ] && die "refusing: $cmd_dir/$c is not a file"
done

if [ -n "$dry" ]; then
    echo "plan: sync $src/ -> $dest/ (removing files the port no longer ships)"
    for c in "${commands[@]}"; do echo "plan: copy $src/commands/$c -> $cmd_dir/$c"; done
else
    command -v rsync >/dev/null 2>&1 || die "rsync is required"
    mkdir -p "$(dirname "$dest")" "$cmd_dir"
    rsync -a --delete --exclude '__pycache__' "$src/" "$dest/"
    for c in "${commands[@]}"; do cp "$src/commands/$c" "$cmd_dir/$c"; done
    echo "vault-portfolio OpenCode port -> $dest"
    echo "commands /vault-portfolio and /vault-compass -> $cmd_dir"
fi

# The records home comes from the port's own config reader, the one definition every
# script uses. Unset or refused, the entry keeps a placeholder and says why.
errf="$(mktemp)"
trap 'rm -f "$errf"' EXIT
set +e
vault_json="$(python3 -I "$src/skills/vault-portfolio/scripts/_config.py" 2>"$errf")"
vault_rc=$?
set -e
vault_err="$(head -n 1 "$errf")"

python3 -I - "$dest" "$config_dir/opencode.json" "$vault_rc" "$vault_json" "$vault_err" <<'PY'
import json, sys
dest, config, rc, out, err = sys.argv[1:]
vault, why = None, None
if rc != "0":
    why = f"the vault config was refused ({err or 'exit ' + rc})"
else:
    try:
        doc = json.loads(out)
    except ValueError:
        doc = None
    if not isinstance(doc, dict) or "vault" not in doc:
        why = "the config reader printed nothing install.sh parses"
    elif doc["vault"] is None:
        why = "no vault is configured"
    elif isinstance(doc["vault"], str) and doc["vault"].startswith("/"):
        vault = doc["vault"].rstrip("/")
    else:
        why = "the configured vault is not an absolute path"
records = f"{vault or '<vault>'}/Portfolio/**"
entries = {
    "skills": {"paths": [f"{dest}/skills"]},
    "permission": {"external_directory": {records: "allow", f"{dest}/**": "allow"}},
}
print()
print(f"Add these entries to {config} yourself; install.sh never edits it.")
print('Merge them into its "skills" and "permission" objects if it already has them:')
print(json.dumps(entries, indent=2))
print()
print("- The first external_directory entry is the records home. Records land there, outside")
print("  any workspace, and OpenCode asks before a tool call there unless the entry allows it.")
print("  `opencode run` refuses without asking and still exits 0: check that a run's records landed.")
print("- The second is the plugin's folder: the rules file and scripts at its root sit outside")
print("  the skill folders OpenCode allows by itself.")
if why:
    print(f"- {why}: replace <vault> with the vault obsidian-wiki uses.")
print("Restart OpenCode, then invoke the skills by name: /vault-portfolio, /vault-compass.")
PY
