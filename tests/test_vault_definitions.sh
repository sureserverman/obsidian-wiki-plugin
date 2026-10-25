#!/usr/bin/env bash
# test_vault_definitions.sh — obsidian-wiki and vault-portfolio agree on the vault
# where they should, and differ only where the difference is deliberate.
#
# Two resolvers read one setting: resolve-vault.sh (obsidian-wiki, vault-context)
# and vault-portfolio's _config.py. They share levels 1 and 2 — $OBSIDIAN_VAULT_PATH,
# then config.json `default_vault` — and must name the same vault there. They
# differ on purpose where vault-portfolio writes: it never guesses a vault (no
# ~/dev/knowledge fallback), it reads the legacy portfolio setting, and it refuses
# a config.json it cannot parse. Each difference is asserted here, so a new one
# cannot appear unnoticed. Every case runs in a throwaway HOME under `env -i`.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SHELL_RESOLVER="$ROOT/plugins/obsidian-wiki/scripts/resolve-vault.sh"
CONFIG="$ROOT/src/vault-portfolio/core/skills/portfolio/scripts/_config.py"

FAILS=0
fail() { echo "FAIL: $*" >&2; FAILS=$((FAILS + 1)); }
ok()   { echo "  ok: $*"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

new_home() { local h="$WORK/$1"; mkdir -p "$h/.config/obsidian-wiki" "$h/.claude"; printf '%s\n' "$h"; }
sh_vault() { local h="$1"; shift; env -i HOME="$h" PATH="$PATH" "$@" bash "$SHELL_RESOLVER" 2>/dev/null; }
py_vault() {
    local h="$1"; shift
    env -i HOME="$h" PATH="$PATH" "$@" python3 -I "$CONFIG" 2>/dev/null \
        | python3 -c 'import json,sys; v=json.load(sys.stdin)["vault"]; print(v if v else "")'
}
py_rc() { local h="$1"; shift; env -i HOME="$h" PATH="$PATH" "$@" python3 -I "$CONFIG" >/dev/null 2>&1; echo $?; }

V="$WORK/vault"; mkdir -p "$V/Portfolio"; V="$(realpath "$V")"

# --- Shared levels: both name the same vault ----------------------------------
h="$(new_home env)"
a="$(sh_vault "$h" OBSIDIAN_VAULT_PATH="$V")"; b="$(py_vault "$h" OBSIDIAN_VAULT_PATH="$V")"
[ -n "$a" ] && [ "$a" = "$b" ] && ok "OBSIDIAN_VAULT_PATH: both name $a" \
    || fail "OBSIDIAN_VAULT_PATH: shell '$a', python '$b'"

h="$(new_home json)"; printf '{"default_vault": "%s"}\n' "$V" > "$h/.config/obsidian-wiki/config.json"
a="$(sh_vault "$h")"; b="$(py_vault "$h")"
[ -n "$a" ] && [ "$a" = "$b" ] && ok "config.json default_vault: both name $a" \
    || fail "config.json default_vault: shell '$a', python '$b'"

h="$(new_home json-tilde)"; mkdir -p "$h/notes"
printf '{"default_vault": "~/notes"}\n' > "$h/.config/obsidian-wiki/config.json"
a="$(sh_vault "$h")"; b="$(py_vault "$h")"
[ "$a" = "$(realpath "$h/notes")" ] && [ "$b" = "$h/notes" ] \
    && ok "config.json default_vault with ~: both name the same directory" \
    || fail "config.json ~ value: shell '$a', python '$b'"

# --- Deliberate differences ------------------------------------------------------
h="$(new_home bare)"; mkdir -p "$h/dev/knowledge"
a="$(sh_vault "$h")"; b="$(py_vault "$h")"
[ "$a" = "$(realpath "$h/dev/knowledge")" ] && [ -z "$b" ] \
    && ok "nothing set: the shell falls back to ~/dev/knowledge, vault-portfolio is unconfigured" \
    || fail "nothing set: shell '$a', python '$b'"

h="$(new_home legacy)"; printf 'vault_dir: %s\n' "$V" > "$h/.claude/portfolio-config.yaml"
b="$(py_vault "$h")"
[ "$b" = "$V" ] && ok "legacy vault_dir: read by vault-portfolio only" \
    || fail "legacy vault_dir: python '$b'"

h="$(new_home malformed)"; printf '{"default_vault": ' > "$h/.config/obsidian-wiki/config.json"
[ "$(py_rc "$h")" = 2 ] && ok "malformed config.json: vault-portfolio refuses it (exit 2)" \
    || fail "malformed config.json: vault-portfolio did not refuse it"

h="$(new_home env-missing)"
sh_vault "$h" OBSIDIAN_VAULT_PATH="$WORK/none" >/dev/null; rc=$?
b="$(py_vault "$h" OBSIDIAN_VAULT_PATH="$WORK/none")"
[ "$rc" -ne 0 ] && [ "$b" = "$WORK/none" ] \
    && ok "missing OBSIDIAN_VAULT_PATH: neither falls through (shell errors, python keeps it)" \
    || fail "missing OBSIDIAN_VAULT_PATH: shell rc=$rc, python '$b'"

[ "$FAILS" -eq 0 ] || { echo "$FAILS failure(s)" >&2; exit 1; }
echo "ALL OK"
