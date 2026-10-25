#!/usr/bin/env bash
# test_setup_host_test_vault.sh — tests/clean-machine/setup-host-test-vault.sh joins the two
# plugins in a scratch CLEAN_HOME the way the clean-machine harness leaves it on Cursor and
# on OpenCode.
#
# The built ports are copied where the harness installs them (Cursor:
# .cursor/plugins/local/vault-portfolio; OpenCode: .local/share/opencode-plugins/vault-portfolio),
# and the synthetic test vault is copied as CLEAN_TEST_VAULT. HOME is the scratch dir too.
#
# Asserts: on both hosts the planning config names the installed copy's records-home.py and
# the resolver probe passes; on OpenCode the merged opencode.json keeps what the harness
# wrote and gains the installer's skills path and its permission.external_directory entry
# for <test vault>/Portfolio/**, and the two command wrappers land in the commands folder;
# an installed copy that differs from the checkout's port is refused; CLEAN_HOST stands
# in for the argument; any other host exits 2.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SETUP="$ROOT/tests/clean-machine/setup-host-test-vault.sh"
S="$(mktemp -d)"
trap 'rm -rf "$S"' EXIT
fails=0
fail() { echo "FAIL: $*" >&2; fails=$((fails + 1)); }
ok() { echo "ok: $*"; }

fresh() {  # fresh <host>: a scratch CLEAN_HOME with the port installed, and its vault copy
    CH="$S/$1/home"; TV="$CH/test-vault"
    rm -rf "$S/$1"; mkdir -p "$CH"
    cp -R "$ROOT/tests/clean-machine/test-vault" "$TV"
    case "$1" in
        cursor) mkdir -p "$CH/.cursor/plugins/local"
                cp -R "$ROOT/ports/cursor/vault-portfolio" "$CH/.cursor/plugins/local/vault-portfolio" ;;
        opencode) mkdir -p "$CH/.local/share/opencode-plugins" "$CH/.config/opencode"
                  cp -R "$ROOT/ports/opencode/vault-portfolio" "$CH/.local/share/opencode-plugins/vault-portfolio"
                  printf '{"plugin": ["/harness/wrote/this.ts"]}\n' > "$CH/.config/opencode/opencode.json" ;;
    esac
}
run() {  # run <host-arg-or-empty> [env...]
    local arg="$1"; shift
    env -i PATH="$PATH" HOME="$CH" CLEAN_HOME="$CH" CLEAN_TEST_VAULT="$TV" "$@" \
        bash "$SETUP" ${arg:+"$arg"} > "$S/out" 2>&1
}

# --- Cursor ---------------------------------------------------------------------------
fresh cursor
if run cursor; then
    grep -qF "$CH/.cursor/plugins/local/vault-portfolio/scripts/records-home.py" "$CH/.config/staged-planning/config.yaml" \
        && grep -q 'probe ok' "$S/out" \
        && ok "cursor: records_resolver names the installed copy and the probe passes" \
        || fail "cursor: config or probe wrong: $(cat "$CH/.config/staged-planning/config.yaml" "$S/out" 2>&1)"
    [ ! -e "$CH/.config/opencode" ] && ok "cursor: nothing OpenCode is written" || fail "cursor: an OpenCode config appeared"
else
    fail "cursor: setup exited $?: $(cat "$S/out")"
fi

# --- OpenCode -------------------------------------------------------------------------
fresh opencode
if run opencode; then
    python3 - "$CH/.config/opencode/opencode.json" "$TV" "$CH" <<'PY' \
        && ok "opencode: opencode.json keeps the harness entry and gains the skills path and external_directory" \
        || fail "opencode: merged opencode.json is wrong: $(cat "$CH/.config/opencode/opencode.json")"
import json, sys
conf, tv, home = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
plugin = home + "/.local/share/opencode-plugins/vault-portfolio"
assert conf["plugin"] == ["/harness/wrote/this.ts"], conf
assert plugin + "/skills" in conf["skills"]["paths"], conf
ext = conf["permission"]["external_directory"]
assert ext.get(tv + "/Portfolio/**") == "allow", ext
assert ext.get(plugin + "/**") == "allow", ext
PY
    [ -f "$CH/.config/opencode/commands/vault-portfolio.md" ] && [ -f "$CH/.config/opencode/commands/vault-compass.md" ] \
        && [ ! -e "$CH/.config/opencode/commands/portfolio.md" ] \
        && ok "opencode: the installer's two command wrappers land, and no rules file does" \
        || fail "opencode: commands folder wrong: $(ls "$CH/.config/opencode/commands" 2>&1)"
    grep -qF "$CH/.local/share/opencode-plugins/vault-portfolio/scripts/records-home.py" "$CH/.config/staged-planning/config.yaml" \
        && ok "opencode: records_resolver names the installed copy" || fail "opencode: records_resolver wrong"
else
    fail "opencode: setup exited $?: $(cat "$S/out")"
fi

# --- the installed copy must be the checkout's port -------------------------------------
fresh opencode
printf 'drift\n' >> "$CH/.local/share/opencode-plugins/vault-portfolio/README.md"
run opencode; rc=$?
[ "$rc" -ne 0 ] && grep -q 'differs from this checkout' "$S/out" \
    && ok "opencode: an installed copy that differs from the checkout's port is refused" \
    || fail "opencode: a drifted installed copy must be refused (rc=$rc): $(cat "$S/out")"

# --- CLEAN_HOST, and a host it does not know --------------------------------------------
fresh opencode
run "" CLEAN_HOST=opencode && grep -q 'external_directory' "$CH/.config/opencode/opencode.json" \
    && ok "CLEAN_HOST stands in for the argument" || fail "CLEAN_HOST fallback failed: $(cat "$S/out")"
run bogus; rc=$?
[ "$rc" -eq 2 ] && ok "an unknown host exits 2" || fail "an unknown host must exit 2 (got $rc)"
fresh cursor
run ""; rc=$?
[ "$rc" -eq 2 ] && ok "no argument and no CLEAN_HOST exits 2" || fail "no host must exit 2 (got $rc)"

[ "$fails" -eq 0 ] && echo "ALL OK" || { echo "$fails failure(s)"; exit 1; }
