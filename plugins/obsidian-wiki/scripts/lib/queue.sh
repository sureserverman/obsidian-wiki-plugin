#!/usr/bin/env bash
# queue.sh — shared queue helpers for obsidian-wiki hooks.
#
# Source this file (don't exec it) from any hook script that needs to write
# or drain queue jobs. All paths key off $XDG_CONFIG_HOME (or ~/.config/) so
# tests can run against an isolated mktemp'd config dir.
#
# Queue layout:
#   <config>/obsidian-wiki/queue/<kind>/<id>.job        — pending
#   <config>/obsidian-wiki/queue/<kind>/done/<id>.job   — drained
#
# All public functions return 0 on success, non-zero on failure.
# Failures never abort the host hook — callers wrap errors as needed.

# Don't `set -e` in a sourced library — it would propagate to the caller.

# ---------------------------------------------------------------------------
# queue_root: print the absolute queue root, creating it if missing.
# ---------------------------------------------------------------------------
queue_root() {
    local cfg="${XDG_CONFIG_HOME:-$HOME/.config}"
    local root="$cfg/obsidian-wiki/queue"
    mkdir -p "$root" 2>/dev/null
    printf '%s\n' "$root"
}

# ---------------------------------------------------------------------------
# queue_dir <kind>: print the per-kind queue dir, creating it (with done/).
# ---------------------------------------------------------------------------
queue_dir() {
    local kind="$1"
    [ -z "$kind" ] && return 1
    local d
    d="$(queue_root)/$kind"
    mkdir -p "$d/done" 2>/dev/null
    printf '%s\n' "$d"
}

# ---------------------------------------------------------------------------
# queue_write <kind> <id> <json-body>
#
# Atomic write: stage to a tmp file under the kind dir, then rename. Multiple
# concurrent writers calling with the same id are serialized via flock so
# exactly one final file ends up on disk. Subsequent writes with the same
# id are no-ops (idempotent enqueue).
# ---------------------------------------------------------------------------
queue_write() {
    local kind="$1" id="$2" body="$3"
    [ -z "$kind" ] && return 1
    [ -z "$id" ] && return 1
    [ -z "$body" ] && return 1

    local d
    d="$(queue_dir "$kind")" || return 1

    local final="$d/$id.job"
    local lock="$d/.$id.lock"

    # Lock per-id so concurrent writers race for the same lock and only the
    # first one writes. The lock file is harmless leftover state — pruned
    # opportunistically by queue_drain.
    (
        flock -x 9 || exit 1
        if [ -f "$final" ]; then
            exit 0
        fi
        local tmp
        tmp="$d/.$id.tmp.$$"
        printf '%s' "$body" > "$tmp" 2>/dev/null || exit 1
        mv -f "$tmp" "$final" 2>/dev/null || { rm -f "$tmp"; exit 1; }
        exit 0
    ) 9>"$lock"
}

# ---------------------------------------------------------------------------
# queue_list <kind>
#
# Print one path per pending job to stdout, sorted oldest-first by mtime.
# Done jobs and dotfiles (locks, tmp) are skipped.
# ---------------------------------------------------------------------------
queue_list() {
    local kind="$1"
    [ -z "$kind" ] && return 1
    local d
    d="$(queue_dir "$kind")" || return 1
    # -maxdepth 1 keeps us out of done/. Skip dotfiles so the per-id locks
    # and partial tmps don't leak into the listing.
    find "$d" -maxdepth 1 -type f -name '*.job' ! -name '.*' \
        -printf '%T@ %p\n' 2>/dev/null \
        | sort -n \
        | awk '{ $1=""; sub(/^ /,""); print }'
}

# ---------------------------------------------------------------------------
# queue_drain_one <kind> <id>
#
# Move a single job from queue/<kind>/<id>.job to queue/<kind>/done/<id>.job.
# Idempotent — a missing pending file or an existing done file is success.
# ---------------------------------------------------------------------------
queue_drain_one() {
    local kind="$1" id="$2"
    [ -z "$kind" ] && return 1
    [ -z "$id" ] && return 1

    local d
    d="$(queue_dir "$kind")" || return 1

    local pending="$d/$id.job"
    local done_path="$d/done/$id.job"

    if [ ! -f "$pending" ]; then
        return 0
    fi
    mv -f "$pending" "$done_path" 2>/dev/null || return 1
    return 0
}

# ---------------------------------------------------------------------------
# queue_drain <kind>
#
# Move every pending .job under queue/<kind>/ into done/. Returns the count
# of moved jobs on stdout.
# ---------------------------------------------------------------------------
queue_drain() {
    local kind="$1"
    [ -z "$kind" ] && return 1
    local d
    d="$(queue_dir "$kind")" || return 1

    local count=0
    local job id
    while IFS= read -r job; do
        [ -z "$job" ] && continue
        id="$(basename "$job" .job)"
        if queue_drain_one "$kind" "$id"; then
            count=$((count + 1))
        fi
    done < <(queue_list "$kind")

    # Opportunistic cleanup: remove .lock files older than 1 day so they
    # don't accumulate forever.
    find "$d" -maxdepth 1 -name '.*.lock' -type f -mtime +1 -delete 2>/dev/null || true

    printf '%d\n' "$count"
}
