#!/usr/bin/env bash
# drain-queue.sh — SessionStart hook for obsidian-wiki.
#
# Drains every pending hook job into a single combined nudge for the
# just-starting Claude Code session:
#
#   1. ONE `{"systemMessage":"..."}` line for the visible TUI nudge
#      (so the user knows obsidian-wiki has work queued).
#   2. ONE plaintext block on stdout for the model's additionalContext,
#      structured so the agent can read it and run the right slash commands.
#
# Three job kinds are recognized today; unknown kinds are listed but their
# directives are reported as "unknown — skipped" so a malformed queue can't
# silently inject random instructions into the next session.
#
#   auto-import         — Claude Code SessionEnd queued a session for import
#   daily-cursor-codex  — daily Cursor/Codex auto-import job (sentinel-gated)
#   daily-index         — daily vault index regen + sidecar refresh job
#
# The drain is best-effort. Any error inside the drain is silenced — never
# blow up the host session start.

set -u  # not -e; this hook must never crash the session

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
LIB_DIR="$script_dir/lib"

# shellcheck source=/dev/null
. "$LIB_DIR/queue.sh" || exit 0

# Read (and discard) hook stdin payload — we don't need any of its fields,
# but Claude Code may pipe JSON in.
cat >/dev/null 2>&1 || true

# Resolve queue root once
QROOT="$(queue_root)" || exit 0

# ---------------------------------------------------------------------------
# describe_<kind> <job-path> -> prints one plaintext line per item.
#
# Each describer reads the .job JSON and renders a concise human/agent-
# readable line. Failures are silent — a malformed job becomes an empty
# line which the caller filters out.
# ---------------------------------------------------------------------------

describe_auto_import() {
    local job="$1"
    [ -f "$job" ] || return 0
    local id sid topic score tpath
    id="$(basename "$job" .job)"
    if command -v jq >/dev/null 2>&1; then
        sid="$(jq -r '.session_id // empty' "$job" 2>/dev/null)"
        topic="$(jq -r '.topic // empty' "$job" 2>/dev/null)"
        score="$(jq -r '.score // empty' "$job" 2>/dev/null)"
        tpath="$(jq -r '.transcript_path // empty' "$job" 2>/dev/null)"
    else
        sid=""; topic=""; score=""; tpath=""
    fi
    [ -z "$sid" ] && sid="$id"
    [ -z "$topic" ] && topic="(unknown topic)"
    [ -z "$score" ] && score="?"
    [ -z "$tpath" ] && tpath="(transcript path missing)"
    printf '    - session=%s score=%s topic=%s transcript=%s\n' \
        "$sid" "$score" "$topic" "$tpath"
}

describe_daily_cursor_codex() {
    local job="$1"
    [ -f "$job" ] || return 0
    local window tools
    if command -v jq >/dev/null 2>&1; then
        window="$(jq -r '.window_days // 1' "$job" 2>/dev/null)"
        tools="$(jq -r '.tools // ["cursor","codex"] | join(",")' "$job" 2>/dev/null)"
    else
        window="1"; tools="cursor,codex"
    fi
    printf '    - window_days=%s tools=%s\n' "$window" "$tools"
}

describe_daily_index() {
    local job="$1"
    [ -f "$job" ] || return 0
    local target
    if command -v jq >/dev/null 2>&1; then
        target="$(jq -r '.target // "vault-index"' "$job" 2>/dev/null)"
    else
        target="vault-index"
    fi
    printf '    - target=%s\n' "$target"
}

# ---------------------------------------------------------------------------
# Collect pending jobs per kind, build the additionalContext block, then
# move drained jobs to done/. We collect first and drain second so a
# describe-time error never loses the file.
# ---------------------------------------------------------------------------

KINDS="auto-import daily-cursor-codex daily-index"

# Per-kind buffers
declare -A LISTING
declare -A COUNTS
declare -A JOB_PATHS  # newline-delimited list per kind

TOTAL=0
for kind in $KINDS; do
    items=""
    paths=""
    n=0
    while IFS= read -r job; do
        [ -z "$job" ] && continue
        case "$kind" in
            auto-import)         line="$(describe_auto_import "$job")" ;;
            daily-cursor-codex)  line="$(describe_daily_cursor_codex "$job")" ;;
            daily-index)         line="$(describe_daily_index "$job")" ;;
            *)                   line="    - unknown kind, skipped" ;;
        esac
        # Skip empty describer output (malformed job)
        [ -z "$line" ] && continue
        items+="$line"$'\n'
        paths+="$job"$'\n'
        n=$((n + 1))
    done < <(queue_list "$kind" 2>/dev/null)

    LISTING[$kind]="$items"
    COUNTS[$kind]="$n"
    JOB_PATHS[$kind]="$paths"
    TOTAL=$((TOTAL + n))
done

if [ "$TOTAL" -eq 0 ]; then
    exit 0
fi

# ---------------------------------------------------------------------------
# Build the directives block. Each kind that has at least one job emits a
# sub-section explaining what the agent should do for those items.
# ---------------------------------------------------------------------------

CTX=""
CTX+="obsidian-wiki: pending jobs"$'\n'

if [ "${COUNTS[auto-import]}" -gt 0 ]; then
    CTX+=$'\n'"- kind: auto-import"$'\n'
    CTX+="  count: ${COUNTS[auto-import]}"$'\n'
    CTX+="  directive: Run /obsidian-wiki:import-session <session-id> for each item below, then /obsidian-wiki:ingest the resulting raw/sessions/ file."$'\n'
    CTX+="  items:"$'\n'
    CTX+="${LISTING[auto-import]}"
fi

if [ "${COUNTS[daily-cursor-codex]}" -gt 0 ]; then
    CTX+=$'\n'"- kind: daily-cursor-codex"$'\n'
    CTX+="  count: ${COUNTS[daily-cursor-codex]}"$'\n'
    CTX+="  directive: Run /obsidian-wiki:scan-sessions cursor <window_days>, then /obsidian-wiki:scan-sessions codex <window_days>, and /obsidian-wiki:import-session each candidate scoring at or above the configured threshold."$'\n'
    CTX+="  items:"$'\n'
    CTX+="${LISTING[daily-cursor-codex]}"
fi

if [ "${COUNTS[daily-index]}" -gt 0 ]; then
    CTX+=$'\n'"- kind: daily-index"$'\n'
    CTX+="  count: ${COUNTS[daily-index]}"$'\n'
    CTX+="  directive: Run /obsidian-wiki:index to regenerate <vault>/index.md."$'\n'
    CTX+="  items:"$'\n'
    CTX+="${LISTING[daily-index]}"
fi

# ---------------------------------------------------------------------------
# Emit the visible systemMessage and the additionalContext block, then drain.
# ---------------------------------------------------------------------------

# JSON-escape the systemMessage. We build a concise summary listing nonzero
# kinds and their counts.
summary_parts=""
for kind in $KINDS; do
    c="${COUNTS[$kind]}"
    [ "$c" -eq 0 ] && continue
    if [ -n "$summary_parts" ]; then summary_parts+=", "; fi
    summary_parts+="$c $kind"
done
msg="[obsidian-wiki] Pending hook jobs: $summary_parts. See additionalContext for directives."
# jq is the safe escaper; fall back to a naive escape if jq is missing.
if command -v jq >/dev/null 2>&1; then
    json_msg="$(printf '%s' "$msg" | jq -Rs .)"
else
    # Naive escape: strip backslashes and quotes. Acceptable since msg is
    # well-formed by construction (no embedded backslashes or quotes).
    safe="$(printf '%s' "$msg" | tr -d '\\"')"
    json_msg="\"$safe\""
fi

# stdout: systemMessage JSON line followed by additionalContext block.
# Claude Code parses ONLY the `{"systemMessage":...}` JSON line; subsequent
# stdout reaches the model's additionalContext.
printf '{"systemMessage":%s}\n' "$json_msg"
printf '%s' "$CTX"

# Now drain everything we listed. We move per-job using the saved paths so
# any race between list and drain is safe (drain_one is idempotent).
for kind in $KINDS; do
    paths="${JOB_PATHS[$kind]}"
    [ -z "$paths" ] && continue
    while IFS= read -r job; do
        [ -z "$job" ] && continue
        id="$(basename "$job" .job)"
        queue_drain_one "$kind" "$id" >/dev/null 2>&1 || true
    done <<< "$paths"
done

exit 0
