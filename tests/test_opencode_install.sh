#!/usr/bin/env bash
# test_opencode_install.sh — ports/opencode/install.sh plans and installs the OpenCode port
# without editing the user's config.
#
# The installer runs from a copy beside a fixture port, built here from what the installer
# needs: the two skills, the two command wrappers, a rules file that must not become a
# command, and the plugin's real config reader (so the printed records home is the vault
# the scripts would use). HOME, XDG_CONFIG_HOME and XDG_DATA_HOME are all in a scratch dir.
#
# Asserts: a dry run writes nothing at all, plans nothing under ~/.claude or ~/.agents,
# prints a parseable snippet with the skills path and permission.external_directory for
# <vault>/Portfolio/**, and leaves opencode.json unchanged; a real install leaves
# opencode.json unchanged too and copies only the two wrappers into the commands folder;
# an unknown argument exits 2; a symlinked target and a target under ~/.claude are refused.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CORE="$ROOT/src/vault-portfolio/core"
S="$(mktemp -d)"
trap 'rm -rf "$S"' EXIT
fails=0
fail() { echo "FAIL: $*" >&2; fails=$((fails + 1)); }
ok() { echo "ok: $*"; }

# --- fixture port -------------------------------------------------------------------
P="$S/repo/ports/opencode"
F="$P/vault-portfolio"
mkdir -p "$F/skills/vault-portfolio/scripts" "$F/skills/vault-compass" "$F/commands" "$F/scripts/lib" "$F/vendor"
cp "$ROOT/ports/opencode/install.sh" "$P/install.sh"
cp "$CORE/skills/portfolio/scripts/_config.py" "$F/skills/vault-portfolio/scripts/_config.py"
cp "$CORE/scripts/lib/registry_path.py" "$F/scripts/lib/registry_path.py"
cp "$CORE/vendor/vendor.lock" "$F/vendor/vendor.lock"
printf -- '---\nname: vault-portfolio\ndescription: fixture\n---\n' > "$F/skills/vault-portfolio/SKILL.md"
printf -- '---\nname: vault-compass\ndescription: fixture\n---\n' > "$F/skills/vault-compass/SKILL.md"
printf -- '---\ndescription: fixture\n---\nLoad the vault-portfolio skill.\n' > "$F/commands/vault-portfolio.md"
printf -- '---\ndescription: fixture\n---\nLoad the vault-compass skill.\n' > "$F/commands/vault-compass.md"
printf -- 'rules, not a command\n' > "$F/commands/portfolio.md"

H="$S/home"; XC="$S/xdg-config"; XD="$S/xdg-data"; V="$S/vault"
mkdir -p "$H" "$XC/opencode" "$XD" "$V/Portfolio"
CFG="$XC/opencode/opencode.json"
printf '{"$schema":"https://opencode.ai/config.json","model":"fixture/model"}\n' > "$CFG"
cfg_sum="$(sha256sum "$CFG")"
DEST="$XD/opencode-plugins/vault-portfolio"

run() {  # extra env assignments, then installer args; output in OUT, status in RC
    local envs=()
    while [ $# -gt 0 ] && [[ "$1" == *=* ]]; do envs+=("$1"); shift; done
    OUT="$(env -i PATH="$PATH" HOME="$H" XDG_CONFIG_HOME="$XC" XDG_DATA_HOME="$XD" \
        "${envs[@]}" bash "$P/install.sh" "$@" 2>&1)"
    RC=$?
}
snapshot() { (cd "$S" && find . -path ./repo -prune -o -print0 | sort -z | xargs -0 ls -ld --time-style=+%s.%N | sha256sum); }

# --- dry run ------------------------------------------------------------------------
before="$(snapshot)"
run OBSIDIAN_VAULT_PATH="$V" --dry-run
[ "$RC" -eq 0 ] && ok "dry run exits 0" || fail "dry run exited $RC: $OUT"
[ "$(snapshot)" = "$before" ] && ok "dry run writes nothing" || fail "dry run changed the scratch HOME or config"
[ "$(sha256sum "$CFG")" = "$cfg_sum" ] && ok "dry run leaves opencode.json unchanged" || fail "dry run edited opencode.json"
if printf '%s\n' "$OUT" | grep -E "$H/\.(claude|agents)(/|$| )" >/dev/null; then
    fail "dry run plans something under ~/.claude or ~/.agents: $OUT"
else
    ok "nothing planned under ~/.claude or ~/.agents"
fi
printf '%s\n' "$OUT" | grep -qF "plan: sync $F/ -> $DEST/" && ok "dry run plans the port's target" \
    || fail "dry run does not plan $DEST: $OUT"
printf '%s\n' "$OUT" | grep -qF "plan: copy $F/commands/vault-portfolio.md -> $XC/opencode/commands/vault-portfolio.md" \
    && ok "dry run plans the vault-portfolio command" || fail "no plan for the vault-portfolio command: $OUT"
printf '%s\n' "$OUT" | grep -q 'external_directory' && ok "snippet names external_directory" \
    || fail "snippet has no external_directory: $OUT"
snippet_check() {  # <expected records-home key>
    printf '%s\n' "$OUT" | python3 -I -c '
import json, sys
want_records, dest = sys.argv[1], sys.argv[2]
lines = sys.stdin.read().split("\n")
start = lines.index("{")
end = lines.index("}", start)
doc = json.loads("\n".join(lines[start:end + 1]))
assert doc["skills"]["paths"] == [dest + "/skills"], doc
ext = doc["permission"]["external_directory"]
assert ext.get(want_records) == "allow", ext
assert ext.get(dest + "/**") == "allow", ext
' "$1" "$DEST"
}
snippet_check "$V/Portfolio/**" && ok "snippet parses: skills path, records home and plugin folder" \
    || fail "snippet does not carry the skills path and both permission entries: $OUT"

# --- no vault, and a config that does not parse: a placeholder, never a guess --------
run --dry-run
snippet_check "<vault>/Portfolio/**" && printf '%s\n' "$OUT" | grep -q 'no vault is configured' \
    && ok "unconfigured vault prints a placeholder and says so" || fail "unconfigured vault: $OUT"
mkdir -p "$H/.config/obsidian-wiki"
printf '{not json' > "$H/.config/obsidian-wiki/config.json"
run --dry-run
snippet_check "<vault>/Portfolio/**" && printf '%s\n' "$OUT" | grep -q 'vault config was refused' \
    && ok "unparsed vault config prints a placeholder and says it was refused" || fail "unparsed config: $OUT"
rm -rf "$H/.config"

# --- arguments and refused targets --------------------------------------------------
run bogus
[ "$RC" -eq 2 ] && ok "unknown argument exits 2" || fail "unknown argument exited $RC"
run OPENCODE_PLUGIN_LOCAL_ROOT="$H/.claude/skills" --dry-run
{ [ "$RC" -ne 0 ] && [ ! -e "$H/.claude" ]; } && ok "a target under ~/.claude is refused" \
    || fail "a target under ~/.claude was accepted (exit $RC): $OUT"
mkdir -p "$S/elsewhere" "$XD/opencode-plugins"
ln -s "$S/elsewhere" "$DEST"
run --dry-run
{ [ "$RC" -ne 0 ] && printf '%s\n' "$OUT" | grep -q 'is a symlink'; } && ok "a symlinked target is refused" \
    || fail "a symlinked target was accepted (exit $RC): $OUT"
rm -f "$DEST"; rmdir "$XD/opencode-plugins"

# --- real install -------------------------------------------------------------------
if command -v rsync >/dev/null 2>&1; then
    run OBSIDIAN_VAULT_PATH="$V"
    [ "$RC" -eq 0 ] && ok "install exits 0" || fail "install exited $RC: $OUT"
    [ "$(sha256sum "$CFG")" = "$cfg_sum" ] && ok "install leaves opencode.json unchanged" || fail "install edited opencode.json"
    { [ ! -e "$H/.claude" ] && [ ! -e "$H/.agents" ]; } && ok "install writes nothing under ~/.claude or ~/.agents" \
        || fail "install wrote under ~/.claude or ~/.agents"
    cmp -s "$F/skills/vault-portfolio/SKILL.md" "$DEST/skills/vault-portfolio/SKILL.md" && ok "port synced to its target" \
        || fail "port not synced to $DEST"
    [ "$(ls "$XC/opencode/commands" | tr '\n' ' ')" = "vault-compass.md vault-portfolio.md " ] \
        && ok "only the two wrappers reach the commands folder" \
        || fail "commands folder holds: $(ls "$XC/opencode/commands" | tr '\n' ' ')"
else
    echo "SKIPPED: real install (rsync missing); the dry-run assertions above still ran" >&2
fi

[ "$fails" -eq 0 ] && { echo "ALL OK"; exit 0; }
echo "$fails failure(s)" >&2
exit 1
