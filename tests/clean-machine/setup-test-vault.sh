#!/usr/bin/env bash
# Setup for the two-plugin clean-machine run (staged-planning's clean-machine-run.sh
# --setup). It runs inside the throwaway HOME after both plugins are installed, with
# CLEAN_HOME and CLEAN_TEST_VAULT set, and writes the two config files that join them:
#   - obsidian-wiki's config, whose default_vault is the harness's test-vault copy;
#   - planning's config, whose records_resolver is vault-portfolio's records-home.py.
# Then it asks that resolver for one home, read-only, so a broken seam fails here
# rather than after a full model session.
#
# The harness takes a file, not a command line, so the resolver's checkout is found
# from the `obsidian-wiki` marketplace the harness registered. That is the harness's
# copy of this repo — `git archive HEAD` when the repo is a git toplevel, so the run
# tests the committed tree — and the run never writes into the checkout it was
# started from. The host that registered it decides where the record is and which
# build's resolver runs:
#   - Claude Code: $CLEAN_HOME/.claude/plugins/known_marketplaces.json (installLocation,
#     then source.path), resolver plugins/vault-portfolio/scripts/records-home.py;
#   - Codex: the [marketplaces.obsidian-wiki] table of $CLEAN_HOME/.codex/config.toml
#     (source), resolver ports/codex/vault-portfolio/scripts/records-home.py.
# A HOME holding both records is refused rather than guessed. A first argument names
# the checkout instead, and a second the resolver's path inside it; with both records,
# the second is required.
set -euo pipefail

: "${CLEAN_HOME:?CLEAN_HOME is not set: run this through clean-machine-run.sh --setup}"
: "${CLEAN_TEST_VAULT:?CLEAN_TEST_VAULT is not set: pass --test-vault to the harness}"
[ -d "$CLEAN_TEST_VAULT/Portfolio" ] || { echo "setup: $CLEAN_TEST_VAULT has no Portfolio/" >&2; exit 1; }

CLAUDE_REL=plugins/vault-portfolio/scripts/records-home.py
CODEX_REL=ports/codex/vault-portfolio/scripts/records-home.py
known="$CLEAN_HOME/.claude/plugins/known_marketplaces.json"
codex_config="$CLEAN_HOME/.codex/config.toml"
if [ $# -ge 1 ]; then
    checkout="$(cd "$1" 2>/dev/null && pwd -P)" || { echo "setup: checkout $1 is not a directory" >&2; exit 1; }
    if [ $# -ge 2 ]; then RESOLVER_REL="$2"
    elif [ -f "$known" ] && [ -f "$codex_config" ]; then
        echo "setup: $CLEAN_HOME holds both a Claude and a Codex marketplace record; pass the resolver's path as a second argument" >&2; exit 1
    elif [ -f "$codex_config" ] && [ ! -f "$known" ]; then RESOLVER_REL="$CODEX_REL"
    else RESOLVER_REL="$CLAUDE_REL"; fi
else
    [ -f "$known" ] && [ -f "$codex_config" ] && {
        echo "setup: $CLEAN_HOME holds both a Claude and a Codex marketplace record; pass the checkout" >&2; exit 1; }
    if [ -f "$codex_config" ]; then RESOLVER_REL="$CODEX_REL"; else RESOLVER_REL="$CLAUDE_REL"; fi
    checkout="$(python3 - "$known" "$codex_config" "$RESOLVER_REL" <<'PY'
import json, os, sys
known, codex_config, rel = sys.argv[1:4]
if os.path.isfile(codex_config):
    try:
        import tomllib
        with open(codex_config, "rb") as fh:
            data = tomllib.load(fh)
    except ImportError:
        sys.exit("setup: reading the Codex config needs Python 3.11 or later (tomllib)")
    except (OSError, ValueError) as e:
        sys.exit(f"setup: cannot read {codex_config}: {e}")
    markets = data.get("marketplaces")
    entry = markets.get("obsidian-wiki") if isinstance(markets, dict) else None
    if not isinstance(entry, dict):
        sys.exit(f"setup: no obsidian-wiki marketplace record in {codex_config}")
    cands = [entry.get("source")]
    where = codex_config
else:
    try:
        with open(known, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        sys.exit(f"setup: cannot read {known}: {e}")
    entry = data.get("obsidian-wiki") if isinstance(data, dict) else None
    if not isinstance(entry, dict):
        sys.exit(f"setup: no obsidian-wiki marketplace record in {known}")
    src = entry.get("source")
    src = src if isinstance(src, dict) else {}
    cands = [entry.get("installLocation"), src.get("path")]
    where = known
for cand in cands:
    if isinstance(cand, str) and os.path.isfile(os.path.join(cand, rel)):
        print(cand)
        sys.exit(0)
sys.exit(f"setup: the obsidian-wiki marketplace in {where} holds no {rel}")
PY
)"
fi
resolver="$checkout/$RESOLVER_REL"
[ -f "$resolver" ] || { echo "setup: $resolver does not exist" >&2; exit 1; }

# Both files are written as JSON: JSON is YAML too, so a path holding `,`, `]` or
# ` #` reaches planning's YAML reader intact.
mkdir -p "$CLEAN_HOME/.config/obsidian-wiki" "$CLEAN_HOME/.config/staged-planning"
python3 - "$CLEAN_HOME" "$CLEAN_TEST_VAULT" "$resolver" <<'PY'
import json, os, sys
home, vault, resolver = sys.argv[1:4]
if "\n" in vault or "\n" in resolver:
    sys.exit("setup: a path holds a newline")
with open(os.path.join(home, ".config/obsidian-wiki/config.json"), "w", encoding="utf-8") as fh:
    json.dump({"default_vault": vault}, fh)
    fh.write("\n")
with open(os.path.join(home, ".config/staged-planning/config.yaml"), "w", encoding="utf-8") as fh:
    fh.write("records_resolver: " + json.dumps(["python3", resolver]) + "\n")
PY

# The read-only probe: no --for-write, so it creates and registers nothing.
probe="$CLEAN_HOME/setup-probe/example-area/example-app"
want="$CLEAN_TEST_VAULT/Portfolio/example-area/example-app"
got="$(python3 "$resolver" --project "$probe")" \
    || { echo "setup: the resolver refused the probe project (exit $?)" >&2; exit 1; }
[ "$got" = "$want" ] || { echo "setup: the resolver answered $got, want $want" >&2; exit 1; }
echo "setup: vault $CLEAN_TEST_VAULT; resolver $resolver; probe ok"
