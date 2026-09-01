#!/usr/bin/env bash
# validate.sh <plugin-root> [--json]
#
# Generic deterministic-lane orchestrator for a plugin. Part of the plugin-dev
# "determinism kit" — vendored into a plugin's scripts/ by install-kit.sh.
#
# It is domain-agnostic: it discovers every sibling validate-*.sh (the plugin's
# own domain validators), runs each with FINDINGS_JSON=1, merges their findings
# on the shared contract, and prints one verdict. Add domain validators with
# scaffold-validator.sh; this orchestrator picks them up automatically.
#
# It deliberately knows nothing about plugin structure — validating plugin
# components is plugin-dev's job (run plugin-dev's validate-plugin.sh from
# outside). This validates THIS plugin's domain.
set -eu
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/lib/findings.sh"
have_jq

JSON=0; ARGS=()
for a in "$@"; do case "$a" in --json) JSON=1 ;; *) ARGS+=("$a") ;; esac; done
ROOT="${ARGS[0]:-.}"
ROOT="$(cd "$ROOT" 2>/dev/null && pwd || true)"
[ -n "$ROOT" ] && [ -d "$ROOT" ] || { echo "usage: $0 <plugin-root> [--json]" >&2; exit 2; }

self="$(basename "${BASH_SOURCE[0]}")"
CHILD_ARRAYS=()
ran=0
run() { # <validator-script-path>
  local out arr
  out=$(FINDINGS_JSON=1 bash "$1" "$ROOT" --json 2>/dev/null || true)
  arr=$(printf '%s' "$out" | jq -c '.findings' 2>/dev/null || true)
  if [ -z "$arr" ] || [ "$arr" = "null" ]; then
    add_finding error orchestrator-validator-error plugin "scripts/$(basename "$1")" 0 "$(basename "$1") produced no valid JSON"
  else
    CHILD_ARRAYS+=("$arr")
  fi
}

for v in "$DIR"/validate-*.sh; do
  [ -e "$v" ] || continue
  [ "$(basename "$v")" = "$self" ] && continue
  run "$v"
  ran=$((ran + 1))
done

if [ "$ran" -eq 0 ]; then
  add_finding info no-domain-validators plugin "scripts/" 0 "no validate-*.sh domain validators yet — add one with scaffold-validator.sh"
fi

MERGED=$(printf '%s\n' "${CHILD_ARRAYS[@]}" "$(_findings_json)" | jq -s 'add // []')

if [ "$JSON" = 1 ]; then
  export FINDINGS_JSON=1
  render_from_json "validate.sh" "$ROOT" "$MERGED"
  exit $?
fi

echo "Plugin: $(basename "$ROOT")  ($ROOT)"
echo "Domain validators: $ran"
echo
render_from_json "validate.sh" "$ROOT" "$MERGED"
