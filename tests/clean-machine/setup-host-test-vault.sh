#!/usr/bin/env bash
# Setup for the two-plugin clean-machine run on Cursor or OpenCode (staged-planning's
# clean-machine-run.sh --setup). It runs inside the throwaway HOME after both plugins are
# installed, with CLEAN_HOME and CLEAN_TEST_VAULT set.
#
#   setup-host-test-vault.sh [cursor|opencode]
#
# The host is the first argument, else CLEAN_HOST (the harness sets it to its --host; it
# takes a file for --setup, not a command line). Anything else exits 2.
#   1. setup-test-vault.sh, beside this file, points obsidian-wiki's config at the test
#      vault copy and planning's records_resolver at the vault-portfolio copy the harness
#      installed in CLEAN_HOME for that host, then probes the resolver read-only:
#        cursor:   $CLEAN_HOME/.cursor/plugins/local/vault-portfolio
#        opencode: $CLEAN_HOME/.local/share/opencode-plugins/vault-portfolio
#   2. On OpenCode only, the documented user step: ports/opencode/install.sh runs with
#      HOME=$CLEAN_HOME (it syncs the port to that same folder and copies its two commands
#      into $CLEAN_HOME/.config/opencode/commands), and the opencode.json entries it prints
#      (the skills path and the permission.external_directory entries for the records home
#      and the plugin folder) are merged into $CLEAN_HOME/.config/opencode/opencode.json.
#      So a run tests what a user does, not a harness shortcut. The installed copy must
#      match this checkout's port first (the installer syncs over it), and a printout this
#      script cannot parse, or one without the records-home and plugin-folder entries,
#      fails it, rather than a run without the permission entry.
set -euo pipefail
: "${CLEAN_HOME:?CLEAN_HOME is not set: run this through clean-machine-run.sh --setup}"
: "${CLEAN_TEST_VAULT:?CLEAN_TEST_VAULT is not set: pass --test-vault to the harness}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
host="${1:-${CLEAN_HOST:-}}"
case "$host" in
    cursor)   plugin="$CLEAN_HOME/.cursor/plugins/local/vault-portfolio" ;;
    opencode) plugin="$CLEAN_HOME/.local/share/opencode-plugins/vault-portfolio" ;;
    *) echo "setup: the host must be cursor or opencode (argument or CLEAN_HOST): '${host}'" >&2; exit 2 ;;
esac
[ -d "$plugin" ] || { echo "setup: no vault-portfolio install at $plugin" >&2; exit 1; }

bash "$here/setup-test-vault.sh" "$plugin" scripts/records-home.py

[ "$host" = opencode ] || exit 0
installer="$here/../../ports/opencode/install.sh"
[ -f "$installer" ] || { echo "setup: $installer not found" >&2; exit 1; }
# The installer syncs this checkout's port over the copy the harness installed. They must
# be the same tree, or the run would test what the installer brought, not what the
# harness installed and verified.
if ! diff -r -x __pycache__ "$plugin" "$here/../../ports/opencode/vault-portfolio" >/dev/null; then
    echo "setup: the installed copy at $plugin differs from this checkout's ports/opencode/vault-portfolio" >&2
    exit 1
fi
printed="$(mktemp)"
trap 'rm -f "$printed"' EXIT
HOME="$CLEAN_HOME" OPENCODE_PLUGIN_LOCAL_ROOT="$CLEAN_HOME/.local/share/opencode-plugins" \
    XDG_CONFIG_HOME="$CLEAN_HOME/.config" bash "$installer" > "$printed"
mkdir -p "$CLEAN_HOME/.config/opencode"
python3 -I - "$CLEAN_HOME/.config/opencode/opencode.json" "$printed" "$plugin" "$CLEAN_TEST_VAULT" <<'PY'
import json, os, sys
config, printed, plugin, vault = sys.argv[1:5]
lines = open(printed, encoding="utf-8").read().splitlines()
try:
    start = lines.index("{")
    end = start + lines[start:].index("}")
    entries = json.loads("\n".join(lines[start:end + 1]))
except ValueError:
    sys.exit("setup: the installer printed no opencode.json entries this script parses")
paths = (entries.get("skills") or {}).get("paths")
ext = (entries.get("permission") or {}).get("external_directory")
if not isinstance(paths, list) or not isinstance(ext, dict) or not ext:
    sys.exit("setup: the printed entries hold no skills.paths or external_directory")
if any("<vault>" in k for k in ext):
    sys.exit("setup: the installer found no vault (its entry keeps <vault>)")
for want in (os.path.realpath(vault) + "/Portfolio/**", plugin + "/**"):
    if not any(os.path.realpath(k[:-3]) + "/**" == os.path.realpath(want[:-3]) + "/**"
               for k in ext if k.endswith("/**")):
        sys.exit(f"setup: the printed external_directory entries lack {want}")
try:
    with open(config) as fh:
        conf = json.load(fh)
except FileNotFoundError:
    conf = {"$schema": "https://opencode.ai/config.json"}
have = conf.setdefault("skills", {}).setdefault("paths", [])
have += [p for p in paths if p not in have]
conf.setdefault("permission", {}).setdefault("external_directory", {}).update(ext)
with open(config, "w") as fh:
    json.dump(conf, fh, indent=2)
    fh.write("\n")
print(f"setup: merged {len(ext)} external_directory entr{'y' if len(ext) == 1 else 'ies'} into opencode.json")
PY
