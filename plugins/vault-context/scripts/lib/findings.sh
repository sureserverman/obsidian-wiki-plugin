#!/usr/bin/env bash
# findings.sh — shared finding accumulator + renderer for the plugin-dev
# deterministic validation suite.
#
# This is the one place the JSON contract lives. Every per-domain validator
# (validate-manifest.sh, validate-skill.sh, …) sources this file, calls
# add_finding repeatedly, then calls render_findings once. The orchestrator
# (validate-plugin.sh) merges the children's JSON and calls render_from_json.
#
# Contract emitted in --json / FINDINGS_JSON=1 mode:
#   {
#     "validator": "<name>",
#     "target":    "<path>",
#     "summary":   {"errors":N,"warnings":N,"info":N},
#     "findings":  [{"severity","rule","category","path","line","message"}, …],
#     "verdict":   "pass" | "pass-with-warnings" | "fail"
#   }
#
# Exit-code convention for callers: error>0 → 1, else 0. render_findings
# returns that code so a validator can `render_findings …; exit $?`.
#
# Severity vocabulary: error (blocks ship) | warn (should fix) | info (nudge).

# --- jq guard ----------------------------------------------------------------
# jq is the only hard dependency; it does all JSON construction so escaping is
# always correct. Exit 3 (distinct from 1=findings, 2=usage) when missing.
have_jq() {
  if ! command -v jq >/dev/null 2>&1; then
    echo "error: jq is required for the plugin-dev validation suite (apt install jq / brew install jq)" >&2
    exit 3
  fi
}

# --- accumulator -------------------------------------------------------------
# Each entry is one compact JSON object, built by jq so any characters in the
# message are escaped correctly.
_FINDINGS=()

# add_finding <severity> <rule> <category> <path> <line> <message>
# line may be empty or non-numeric; it is coerced to 0.
add_finding() {
  local severity="$1" rule="$2" category="$3" path="$4" line="$5" message="$6"
  case "$line" in
    ''|*[!0-9]*) line=0 ;;
  esac
  _FINDINGS+=("$(jq -nc \
    --arg severity "$severity" \
    --arg rule "$rule" \
    --arg category "$category" \
    --arg path "$path" \
    --argjson line "$line" \
    --arg message "$message" \
    '{severity:$severity,rule:$rule,category:$category,path:$path,line:$line,message:$message}')")
}

# _findings_json — collapse the accumulator into a JSON array (or []).
_findings_json() {
  if [ "${#_FINDINGS[@]}" -gt 0 ]; then
    printf '%s\n' "${_FINDINGS[@]}" | jq -s '.'
  else
    echo '[]'
  fi
}

# --- rendering ---------------------------------------------------------------
# render_from_json <validator> <target> <findings-json-array>
# The single rendering path. Honors FINDINGS_JSON=1 (machine) vs default
# (human). Returns 1 iff there is at least one error.
render_from_json() {
  local validator="$1" target="$2" findings="$3"
  local errors warnings info verdict
  errors=$(printf '%s' "$findings"  | jq '[.[]|select(.severity=="error")]|length')
  warnings=$(printf '%s' "$findings" | jq '[.[]|select(.severity=="warn")]|length')
  info=$(printf '%s' "$findings"    | jq '[.[]|select(.severity=="info")]|length')

  verdict="pass"
  [ "$warnings" -gt 0 ] && verdict="pass-with-warnings"
  [ "$errors" -gt 0 ]   && verdict="fail"

  if [ "${FINDINGS_JSON:-0}" = "1" ]; then
    jq -n \
      --arg validator "$validator" \
      --arg target "$target" \
      --argjson errors "$errors" \
      --argjson warnings "$warnings" \
      --argjson info "$info" \
      --argjson findings "$findings" \
      --arg verdict "$verdict" \
      '{validator:$validator,target:$target,
        summary:{errors:$errors,warnings:$warnings,info:$info},
        findings:$findings,verdict:$verdict}'
  else
    echo "── $validator: $target"
    if [ "$((errors + warnings + info))" -eq 0 ]; then
      echo "   ✅ clean"
    else
      printf '%s' "$findings" | jq -r '
        sort_by(if .severity=="error" then 0 elif .severity=="warn" then 1 else 2 end)[]
        | (if .severity=="error" then "   ❌" elif .severity=="warn" then "   ⚠️ " else "   💡" end)
          + " [" + .rule + "] " + .path
          + (if .line > 0 then ":" + (.line|tostring) else "" end)
          + " — " + .message'
    fi
    echo "   verdict: $verdict ($errors error(s), $warnings warning(s), $info info)"
  fi

  [ "$errors" -gt 0 ] && return 1 || return 0
}

# render_findings <validator> <target>
# Convenience wrapper for a standalone validator: render the accumulator.
render_findings() {
  render_from_json "$1" "$2" "$(_findings_json)"
}

# --- frontmatter helpers -----------------------------------------------------
# extract_frontmatter <file> — print the YAML between the first two --- lines.
# Prints nothing if the file does not open with a --- fence.
extract_frontmatter() {
  awk '
    NR==1 && $0!="---" { exit }
    /^---[[:space:]]*$/ { c++; next }
    c==1 { print }
    c>=2 { exit }
  ' "$1"
}

# frontmatter_field <file> <key> — first value for <key>, quotes stripped.
# Safe under `set -e`/`pipefail`: a missing key yields an empty string, not a
# non-zero pipeline.
frontmatter_field() {
  local raw
  raw=$(extract_frontmatter "$1" | grep "^$2:" | head -1 || true)
  [ -n "$raw" ] || return 0
  printf '%s' "$raw" | sed "s/^$2:[[:space:]]*//; s/^\"\(.*\)\"$/\1/; s/^'\(.*\)'$/\1/"
}

# has_closing_fence <file> — true iff a frontmatter block is opened and closed.
has_closing_fence() {
  [ "$(head -1 "$1")" = "---" ] && tail -n +2 "$1" | grep -q '^---[[:space:]]*$'
}

# --- description heuristics (shared by skill/agent/command validators) -------
# These are deliberately *candidate* checks: high-precision regexes that flag a
# description for the LLM lane to confirm. The model decides if it is a genuine
# POV/leak problem and how to rewrite — the script only points.
#
# check_description <path> <line> <category> <description>
check_description() {
  local path="$1" line="$2" category="$3" desc="$4" bare
  # Trigger phrases are conventionally double-quoted and legitimately contain
  # first-person ("…before I can ship") — strip quoted spans so we only test the
  # skill's own narration for POV/leak signals.
  bare=$(printf '%s' "$desc" | sed 's/"[^"]*"//g')
  if printf '%s\n' "$bare" | grep -Eiq "\b(i help|i will|i can|i am|i'm|i'll|we help|we will|we can|my own|our )\b"; then
    add_finding warn desc-first-person "$category" "$path" "$line" \
      "description appears first-person ('I…/we…/our…') — skill & agent descriptions are third-person ('Use when …'); confirm"
  fi
  if printf '%s\n' "$bare" | grep -Eiq "[0-9]+-(step|phase|stage)|\bstep [0-9]|\bfirst\b.*\bthen\b|, then "; then
    add_finding warn desc-leak-candidate "$category" "$path" "$line" \
      "description may leak workflow/procedure (ordered steps) — keep 'when', move 'how' to the body; confirm via skill-description-leak-audit"
  fi
}
