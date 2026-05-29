#!/usr/bin/env bash
# validate-log.sh <vault-root> [--json]
# Deterministic checks for the vault's log.md — the append-only activity log
# that /log, /ingest, /merge, /lint, /index and the session skills all write.
# Every entry heading must match `## [YYYY-MM-DD] <type> | <title>` and use a
# <type> from the known vocabulary. These are the mechanical rules each of those
# skills currently restates in prose; this is the single source of truth for
# them. What an entry should SAY stays with the skill that writes it.
set -eu
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/lib/findings.sh"
have_jq

JSON=0; ARGS=()
for a in "$@"; do case "$a" in --json) JSON=1 ;; *) ARGS+=("$a") ;; esac; done
[ "$JSON" = 1 ] && export FINDINGS_JSON=1
ROOT="${ARGS[0]:-.}"
ROOT="$(cd "$ROOT" 2>/dev/null && pwd || true)"
[ -n "$ROOT" ] && [ -d "$ROOT" ] || { echo "usage: $0 <vault-root> [--json]" >&2; exit 2; }

LOG="$ROOT/log.md"
# Only activates on a vault that has a log.md. (A vault without one is fine —
# /ingest creates it; this validator simply has nothing to check.)
[ -f "$LOG" ] || { render_findings "validate-log.sh" "$ROOT"; exit $?; }

# The entry-type vocabulary. Adding a type means appending here AND updating the
# /log skill — keeping both honest is exactly why this lives in one script.
TYPES="ingest query lint schema merge gaps session-import session-capture index"
in_enum() { case " $TYPES " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

# Walk every level-2 heading (entries are `## …`; deeper `###` are entry bodies).
while IFS=: read -r ln line; do
  [ -n "$ln" ] || continue
  # Expected shape: ## [YYYY-MM-DD] <type> | <title>
  if printf '%s' "$line" | grep -Eq '^## \[[0-9]{4}-[0-9]{2}-[0-9]{2}\] [^|]+ \| .+'; then
    type="$(printf '%s' "$line" | sed -E 's/^## \[[0-9-]+\] ([^|]+) \|.*/\1/; s/[[:space:]]*$//')"
    if ! in_enum "$type"; then
      add_finding warn log-unknown-type log "log.md" "$ln" \
        "entry type '$type' is not in the known set ($TYPES) — add it to the /log skill if intentional, else fix the typo"
    fi
  else
    add_finding warn log-malformed-entry log "log.md" "$ln" \
      "entry heading does not match '## [YYYY-MM-DD] <type> | <title>': ${line}"
  fi
done < <(grep -nE '^## ' "$LOG" 2>/dev/null || true)

render_findings "validate-log.sh" "$ROOT"; exit $?
