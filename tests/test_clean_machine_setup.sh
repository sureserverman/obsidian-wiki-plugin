#!/usr/bin/env bash
# test_clean_machine_setup.sh — tests/clean-machine/setup-test-vault.sh, the
# --setup script of the two-plugin clean-machine run, outside that (paid, live)
# run. It runs the script the way the harness does — in a throwaway HOME under
# `env -i`, with CLEAN_HOME and CLEAN_TEST_VAULT set — against a committed-tree
# copy of this repo placed where the harness's marketplace record points.
#
# What it pins:
#   - the planning config parses back to the exact resolver argv, even when the
#     checkout path holds YAML flow characters (`,`, ` #`, `]`);
#   - the script proves the resolver answers before the session starts: a
#     resolver that refuses fails the setup;
#   - a relative checkout argument is written as an absolute path;
#   - a malformed marketplace record fails with a `setup:` message, never a
#     traceback;
#   - the seed vault does not tell a reader where records land, so a run can
#     only find the vault through the resolver.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SETUP="$ROOT/tests/clean-machine/setup-test-vault.sh"
SEED="$ROOT/tests/clean-machine/test-vault"
RESOLVER_REL=plugins/vault-portfolio/scripts/records-home.py

FAILS=0
fail() { echo "FAIL: $*" >&2; FAILS=$((FAILS + 1)); }
ok()   { echo "  ok: $*"; }

python3 -c 'import yaml' 2>/dev/null || { echo "FAIL: PyYAML is required" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# A committed-tree copy of this repo, in a directory whose name YAML's flow
# syntax would split or cut short if written unquoted.
COPY="$WORK/co, py #1]"
mkdir -p "$COPY"
git -C "$ROOT" archive HEAD | tar -x -C "$COPY" || { echo "FAIL: git archive" >&2; exit 1; }

# new_home <name> <marketplace json> — a throwaway HOME holding the seed copy
# and a marketplace record; prints the HOME path.
new_home() {
    local h="$WORK/$1"
    mkdir -p "$h/.claude/plugins"
    cp -R "$SEED" "$h/test-vault"
    printf '%s\n' "$2" > "$h/.claude/plugins/known_marketplaces.json"
    printf '%s\n' "$h"
}

record() {
    python3 -c 'import json,sys; print(json.dumps({"obsidian-wiki": {"source": {"source": "directory", "path": sys.argv[1]}, "installLocation": sys.argv[1]}}))' "$1"
}

# run_setup <home> [arg] — the harness's call: cwd = HOME, env -i.
run_setup() {
    local h="$1"; shift
    ( cd "$h" && env -i PATH="$PATH" HOME="$h" CLEAN_HOME="$h" CLEAN_TEST_VAULT="$h/test-vault" \
        bash "$SETUP" "$@" )
}

# 1. The configs, with a hostile checkout path.
h="$(new_home main "$(record "$COPY")")"
if out="$(run_setup "$h" 2>&1)"; then
    ok "setup exits 0 on a well-formed HOME"
else
    fail "setup failed on a well-formed HOME: $out"
fi
got="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["default_vault"])' \
    "$h/.config/obsidian-wiki/config.json" 2>&1)"
[ "$got" = "$h/test-vault" ] && ok "default_vault is the test-vault copy" \
    || fail "default_vault is $got, want $h/test-vault"
python3 - "$h/.config/staged-planning/config.yaml" "$COPY/$RESOLVER_REL" 2>/dev/null <<'PY' \
    && ok "records_resolver parses back to [python3, <checkout resolver>]" \
    || fail "records_resolver does not parse back to the exact argv"
import sys, yaml
with open(sys.argv[1], encoding="utf-8") as fh:
    cfg = yaml.safe_load(fh)
sys.exit(0 if cfg == {"records_resolver": ["python3", sys.argv[2]]} else 1)
PY

# 2. A resolver that refuses fails the setup.
STUB="$WORK/stub"
mkdir -p "$STUB/$(dirname "$RESOLVER_REL")"
printf 'import sys\nsys.exit("refused")\n' > "$STUB/$RESOLVER_REL"
h="$(new_home stub "$(record "$STUB")")"
if out="$(run_setup "$h" 2>&1)"; then
    fail "setup passed although the resolver refused: $out"
else
    ok "a refusing resolver fails the setup"
fi

# 3. A relative checkout argument is made absolute.
h="$(new_home relative "$(record "$COPY")")"
rel="$(python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "$COPY" "$h")"
if out="$(run_setup "$h" "$rel" 2>&1)"; then
    python3 - "$h/.config/staged-planning/config.yaml" 2>/dev/null <<'PY' \
        && ok "a relative checkout is written as an absolute path" \
        || fail "a relative checkout was written as a relative path"
import os, sys, yaml
with open(sys.argv[1], encoding="utf-8") as fh:
    argv = yaml.safe_load(fh)["records_resolver"]
sys.exit(0 if os.path.isabs(argv[1]) else 1)
PY
else
    fail "setup failed on a relative checkout: $out"
fi

# 4. A malformed marketplace record is a setup: message, not a traceback.
n=0
for shape in '[]' '{"obsidian-wiki": "x"}' '{}'; do
    n=$((n + 1))
    h="$(new_home "bad$n" "$shape")"
    if out="$(run_setup "$h" 2>&1)"; then
        fail "setup passed on marketplace record $shape"
    elif grep -q 'Traceback' <<<"$out" || ! grep -q '^setup:' <<<"$out"; then
        fail "marketplace record $shape: no setup: message: $out"
    else
        ok "marketplace record $shape fails with a setup: message"
    fi
done

# 5. A Codex home: the marketplace record is Codex's config.toml table, and the
# resolver is the Codex build's copy.
CODEX_REL=ports/codex/vault-portfolio/scripts/records-home.py
codex_home() {
    local h="$WORK/$1"
    mkdir -p "$h/.codex"
    cp -R "$SEED" "$h/test-vault"
    python3 -c 'import json,sys; print("[marketplaces.obsidian-wiki]\nsource_type = \"local\"\nsource = " + json.dumps(sys.argv[1]))' \
        "$2" > "$h/.codex/config.toml"
    printf '%s\n' "$h"
}
h="$(codex_home codex "$COPY")"
if out="$(run_setup "$h" 2>&1)"; then
    python3 - "$h/.config/staged-planning/config.yaml" "$COPY/$CODEX_REL" 2>/dev/null <<'PY' \
        && ok "a Codex home's resolver is the Codex build's records-home.py" \
        || fail "a Codex home's records_resolver is not [python3, <checkout>/$CODEX_REL]"
import sys, yaml
with open(sys.argv[1], encoding="utf-8") as fh:
    cfg = yaml.safe_load(fh)
sys.exit(0 if cfg == {"records_resolver": ["python3", sys.argv[2]]} else 1)
PY
else
    fail "setup failed on a Codex home: $out"
fi
h="$(codex_home codex-explicit "$COPY")"
if out="$(run_setup "$h" "$COPY" "$CODEX_REL" 2>&1)" \
        && grep -qF "$COPY/$CODEX_REL" "$h/.config/staged-planning/config.yaml"; then
    ok "a second argument names the resolver's path in the checkout"
else
    fail "setup with <checkout> <resolver path> did not use that resolver: $out"
fi
h="$(codex_home both "$COPY")"
mkdir -p "$h/.claude/plugins" && record "$COPY" > "$h/.claude/plugins/known_marketplaces.json"
if out="$(run_setup "$h" 2>&1)"; then
    fail "setup guessed a host although both a Claude and a Codex record exist"
elif grep -q '^setup:' <<<"$out" && ! grep -q Traceback <<<"$out"; then
    ok "a HOME with both hosts' records fails with a setup: message"
else
    fail "a HOME with both hosts' records: no setup: message: $out"
fi
if out="$(run_setup "$h" "$COPY" 2>&1)"; then
    fail "setup guessed a resolver for a checkout although both hosts' records exist"
elif grep -q '^setup:' <<<"$out" && ! grep -q Traceback <<<"$out"; then
    ok "a checkout alone, with both hosts' records, fails with a setup: message"
else
    fail "a checkout alone with both hosts' records: no setup: message: $out"
fi
h="$WORK/codex-bad"; mkdir -p "$h/.codex"; cp -R "$SEED" "$h/test-vault"
printf 'not = [toml\n' > "$h/.codex/config.toml"
if out="$(run_setup "$h" 2>&1)"; then
    fail "setup passed on a malformed Codex config"
elif grep -q '^setup:' <<<"$out" && ! grep -q Traceback <<<"$out"; then
    ok "a malformed Codex config fails with a setup: message"
else
    fail "a malformed Codex config: no setup: message: $out"
fi
printf 'marketplaces = "x"\n' > "$h/.codex/config.toml"
if out="$(run_setup "$h" 2>&1)"; then
    fail "setup passed on a Codex config whose marketplaces is not a table"
elif grep -q '^setup:' <<<"$out" && ! grep -q Traceback <<<"$out"; then
    ok "a Codex config whose marketplaces is not a table fails with a setup: message"
else
    fail "marketplaces not a table: no setup: message: $out"
fi

# 6. The seed says what the folder is, not where records go.
if grep -rqiE 'record|land|<area>|<name>' "$SEED"; then
    fail "the seed vault names where records land"
else
    ok "the seed vault does not name where records land"
fi

[ "$FAILS" -eq 0 ] || { echo "$FAILS failure(s)" >&2; exit 1; }
echo "ALL OK"
