#!/usr/bin/env bash
# daily-gate.sh — per-task daily sentinel helper.
#
# A "daily gate" is a per-kind, per-UTC-day sentinel file. The first caller
# on a given UTC day acquires the gate (returns 0); subsequent callers the
# same day return 1. Old sentinels for prior days are pruned opportunistically
# whenever a new day's sentinel is written.
#
# Sentinel layout:
#   <config>/obsidian-wiki/state/daily-<kind>-<UTC-YYYY-MM-DD>.done
#
# Source this file (don't exec it). All paths key off $XDG_CONFIG_HOME so
# tests run in isolation.

# Don't `set -e` in a sourced library.

# ---------------------------------------------------------------------------
# daily_gate_state_dir: print the absolute state dir, creating it if missing.
# ---------------------------------------------------------------------------
daily_gate_state_dir() {
    local cfg="${XDG_CONFIG_HOME:-$HOME/.config}"
    local d="$cfg/obsidian-wiki/state"
    mkdir -p "$d" 2>/dev/null
    printf '%s\n' "$d"
}

# ---------------------------------------------------------------------------
# daily_gate_today_filename <kind>: print the sentinel filename for today.
# Override the date via $DAILY_GATE_DATE (test-only).
# ---------------------------------------------------------------------------
daily_gate_today_filename() {
    local kind="$1"
    [ -z "$kind" ] && return 1
    local d
    d="$(daily_gate_state_dir)" || return 1
    local today="${DAILY_GATE_DATE:-$(date -u +%Y-%m-%d)}"
    printf '%s/daily-%s-%s.done\n' "$d" "$kind" "$today"
}

# ---------------------------------------------------------------------------
# daily_gate_acquire <kind>
#
# Returns 0 if today's sentinel did not exist (and writes it).
# Returns 1 if today's sentinel already exists (gate closed for today).
# Prunes sentinels of the same kind for OTHER dates whenever it acquires.
# ---------------------------------------------------------------------------
daily_gate_acquire() {
    local kind="$1"
    [ -z "$kind" ] && return 1

    local f
    f="$(daily_gate_today_filename "$kind")" || return 1

    if [ -f "$f" ]; then
        return 1
    fi

    : > "$f" 2>/dev/null || return 1

    # Prune old sentinels of the same kind. We deliberately use -not -name
    # rather than mtime — the file's date is encoded in its name, which is
    # more reliable than filesystem mtime (the user could `touch` for testing).
    local d today
    d="$(daily_gate_state_dir)"
    today="${DAILY_GATE_DATE:-$(date -u +%Y-%m-%d)}"
    find "$d" -maxdepth 1 -type f -name "daily-${kind}-*.done" \
        -not -name "daily-${kind}-${today}.done" -delete 2>/dev/null || true

    return 0
}

# ---------------------------------------------------------------------------
# daily_gate_status <kind>: print "open" if today's gate has not been
# acquired, "closed" otherwise. Read-only.
# ---------------------------------------------------------------------------
daily_gate_status() {
    local kind="$1"
    [ -z "$kind" ] && return 1
    local f
    f="$(daily_gate_today_filename "$kind")" || return 1
    if [ -f "$f" ]; then
        printf 'closed\n'
    else
        printf 'open\n'
    fi
}
