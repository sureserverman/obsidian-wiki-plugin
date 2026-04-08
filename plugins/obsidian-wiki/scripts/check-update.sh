#!/usr/bin/env bash
# check-update.sh — SessionStart hook for obsidian-wiki.
#
# Three phases, all best-effort, none allowed to crash the host session:
#
#   1. READ CACHE: parse /tmp/claude/obsidian-wiki-update-check.json if it
#      exists. Cross-check the cache's recorded local_sha against the
#      marketplace clone's actual HEAD; if they differ, treat the cache as
#      stale (it was written before the clone moved, e.g. by
#      `claude plugin update`).
#
#   2. SYNCHRONOUS FAST REFRESH (bounded): if the cache is missing OR stale,
#      attempt a 2-second timeout-bounded `git fetch` inline. On success, we
#      can print the nudge in THIS session — no two-session delay after a push.
#      If `timeout` is unavailable, or the fetch is slow/offline, we fall
#      through to the async path so the session still starts without waiting.
#
#   3. PRINT: if the cache (freshly written or still valid) says
#      update_available=true, emit a JSON systemMessage hook response so the
#      nudge is rendered in the user's TUI. Plain-text stdout from a
#      SessionStart hook only reaches the model's additionalContext — it is
#      NEVER shown to the user. The TUI only renders `{"systemMessage": "..."}`
#      as a visible "SessionStart:startup says: …" gray line.
#
#   4. ASYNC FALLBACK REFRESH: if the sync path didn't write a cache and the
#      existing cache is missing/stale/expired, spawn a detached background
#      `git fetch` so the next session has fresh data.
#
# The script NEVER modifies any plugin, marketplace, or user file. It only
# writes its own cache file under /tmp/claude/.

set -u  # fail on undefined vars, but NOT -e — we want best-effort behavior

CACHE_DIR="/tmp/claude"
CACHE_FILE="$CACHE_DIR/obsidian-wiki-update-check.json"
MARKETPLACE_DIR="$HOME/.claude/plugins/marketplaces/obsidian-wiki"
TTL_SECONDS=21600  # 6 hours
SYNC_FETCH_TIMEOUT=2  # seconds we are willing to block session start on fetch

update_available="false"
commits_ahead="0"
cached_local_sha=""

# ---------------------------------------------------------------------------
# parse_cache_file: populate update_available / commits_ahead / cached_local_sha
# from $CACHE_FILE. Silent on missing or malformed input.
# ---------------------------------------------------------------------------
parse_cache_file() {
    [ -f "$CACHE_FILE" ] || return 1
    if command -v jq >/dev/null 2>&1; then
        update_available="$(jq -r '.update_available // false' "$CACHE_FILE" 2>/dev/null || printf 'false')"
        commits_ahead="$(jq -r '.commits_ahead // 0' "$CACHE_FILE" 2>/dev/null || printf '0')"
        cached_local_sha="$(jq -r '.local_sha // empty' "$CACHE_FILE" 2>/dev/null || printf '')"
    elif command -v python3 >/dev/null 2>&1; then
        read -r update_available commits_ahead cached_local_sha < <(
            python3 -c "
import json
try:
    d = json.load(open('$CACHE_FILE'))
    print(str(d.get('update_available', False)).lower(), d.get('commits_ahead', 0), d.get('local_sha', ''))
except Exception:
    print('false 0 ')
" 2>/dev/null || printf 'false 0 \n'
        )
    else
        update_available="false"
        commits_ahead="0"
        cached_local_sha=""
    fi
    return 0
}

# ---------------------------------------------------------------------------
# resolve_remote_ref: echo the canonical remote ref for the marketplace clone,
# trying in order: configured upstream → symbolic origin/HEAD → origin/master
# → origin/main. Returns non-zero if none of those resolve.
# ---------------------------------------------------------------------------
resolve_remote_ref() {
    local ref
    if ref="$(git -C "$MARKETPLACE_DIR" rev-parse --abbrev-ref --symbolic-full-name @{upstream} 2>/dev/null)"; then
        printf '%s' "$ref"; return 0
    fi
    if ref="$(git -C "$MARKETPLACE_DIR" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null)"; then
        printf '%s' "$ref"; return 0
    fi
    if git -C "$MARKETPLACE_DIR" rev-parse --verify --quiet origin/master >/dev/null 2>&1; then
        printf 'origin/master'; return 0
    fi
    if git -C "$MARKETPLACE_DIR" rev-parse --verify --quiet origin/main >/dev/null 2>&1; then
        printf 'origin/main'; return 0
    fi
    return 1
}

# ---------------------------------------------------------------------------
# compute_and_write_cache: given that a successful fetch has just been done,
# compute the verdict and atomically rewrite $CACHE_FILE. Returns non-zero if
# any step fails (caller falls back to async path).
# ---------------------------------------------------------------------------
compute_and_write_cache() {
    local local_sha remote_ref remote_sha commits upd now tmp
    local_sha="$(git -C "$MARKETPLACE_DIR" rev-parse HEAD 2>/dev/null)" || return 1
    remote_ref="$(resolve_remote_ref)" || return 1
    remote_sha="$(git -C "$MARKETPLACE_DIR" rev-parse "$remote_ref" 2>/dev/null)" || return 1

    if [ "$local_sha" = "$remote_sha" ]; then
        upd="false"; commits=0
    else
        commits="$(git -C "$MARKETPLACE_DIR" rev-list --count "$local_sha..$remote_sha" 2>/dev/null || printf 0)"
        if [ "$commits" = "0" ]; then upd="false"; else upd="true"; fi
    fi
    now="$(date +%s)"
    tmp="${CACHE_FILE}.tmp.$$"
    cat > "$tmp" <<EOF
{
  "update_available": $upd,
  "local_sha": "$local_sha",
  "remote_sha": "$remote_sha",
  "remote_ref": "$remote_ref",
  "commits_ahead": $commits,
  "checked": $now
}
EOF
    mv "$tmp" "$CACHE_FILE" 2>/dev/null || { rm -f "$tmp"; return 1; }
    return 0
}

# ---------------------------------------------------------------------------
# sync_refresh: do a BLOCKING, time-bounded fetch + cache rewrite. Returns
# non-zero if anything fails — the marketplace clone is missing, no `timeout`
# command is available, the fetch times out or errors, or the verdict cannot
# be computed. The caller MUST treat failure as "fall through to async".
# ---------------------------------------------------------------------------
sync_refresh() {
    [ -d "$MARKETPLACE_DIR/.git" ] || return 1
    git -C "$MARKETPLACE_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 1
    git -C "$MARKETPLACE_DIR" remote get-url origin >/dev/null 2>&1 || return 1

    # We require a `timeout`-style command so a hung network never blocks
    # session start beyond $SYNC_FETCH_TIMEOUT seconds. Prefer GNU `timeout`,
    # fall back to brew `gtimeout`; if neither exists, skip sync refresh.
    local timeout_cmd=""
    if command -v timeout >/dev/null 2>&1; then
        timeout_cmd="timeout"
    elif command -v gtimeout >/dev/null 2>&1; then
        timeout_cmd="gtimeout"
    else
        return 1
    fi

    mkdir -p "$CACHE_DIR" 2>/dev/null || return 1

    "$timeout_cmd" "$SYNC_FETCH_TIMEOUT" \
        git -C "$MARKETPLACE_DIR" fetch --quiet --no-tags --prune origin >/dev/null 2>&1 || return 1

    compute_and_write_cache || return 1
    return 0
}

# ---------------------------------------------------------------------------
# PHASE 1: read cache (if any) and detect staleness vs marketplace HEAD.
# ---------------------------------------------------------------------------
cache_stale=0
if parse_cache_file; then
    # Cross-check: cached local_sha vs marketplace clone's actual HEAD.
    # If they differ, the cache is stale relative to the clone (e.g. user
    # ran `claude plugin update` since the cache was written), so we cannot
    # trust update_available.
    if [ -d "$MARKETPLACE_DIR/.git" ] && [ -n "$cached_local_sha" ]; then
        current_head="$(git -C "$MARKETPLACE_DIR" rev-parse HEAD 2>/dev/null || printf '')"
        if [ -n "$current_head" ] && [ "$current_head" != "$cached_local_sha" ]; then
            cache_stale=1
        fi
    fi
fi

# ---------------------------------------------------------------------------
# PHASE 2 (SYNC FAST PATH): try a 2s-bounded inline refresh on every session
# start, regardless of cache freshness or staleness state.
#
# Why every session, not just "missing or stale": the previous gating left a
# poisoning hole — a cache written BEFORE the user pushed says
# update_available=false with a local_sha that still matches the marketplace
# HEAD (because nothing has moved the clone yet). The staleness check passes,
# the 6h async TTL hasn't expired, so the false-negative cache silently
# suppresses the nudge for up to 6 hours after a push. Bounding the fetch at
# $SYNC_FETCH_TIMEOUT seconds is the only safety net we need; an unchanged
# origin fetch is one small HTTPS request and finishes in well under a second.
#
# If sync_refresh fails (no `timeout` cmd, offline, slow network), we fall
# through to print whatever the existing cache says — last-known-state is
# better than nothing — and Phase 4 still spawns the async fallback.
# ---------------------------------------------------------------------------
sync_refreshed=0
if sync_refresh; then
    sync_refreshed=1
    cache_stale=0
    parse_cache_file  # re-read the freshly-written values
fi

# ---------------------------------------------------------------------------
# PHASE 3 (PRINT): nudge the user iff the (possibly freshly refreshed) cache
# says an update is available and we trust it.
# ---------------------------------------------------------------------------
if [ "$cache_stale" -eq 0 ] && [ "$update_available" = "true" ]; then
    if [ "$commits_ahead" = "1" ]; then
        msg='[obsidian-wiki] Update available: 1 commit behind. Run `/obsidian-wiki:update` to see what is new.'
    else
        msg='[obsidian-wiki] Update available: '"$commits_ahead"' commits behind. Run `/obsidian-wiki:update` to see what is new.'
    fi
    # JSON systemMessage — the only SessionStart hook output that is visible
    # to the user in the TUI. Plain-text stdout would go silently into the
    # model's additionalContext and never reach the user.
    printf '{"systemMessage":"%s"}\n' "$msg"
fi

# ---------------------------------------------------------------------------
# PHASE 4 (ASYNC FALLBACK): if the sync path already wrote a fresh cache,
# nothing to do. Otherwise, decide whether to spawn a detached refresh based
# on TTL / staleness. This is the original async path — kept verbatim so a
# `timeout`-less macOS install still benefits from background refreshing.
# ---------------------------------------------------------------------------
if [ "$sync_refreshed" -eq 1 ]; then
    exit 0
fi

need_refresh=1
if [ -f "$CACHE_FILE" ] && [ "$cache_stale" -eq 0 ]; then
    # stat -c works on Linux (GNU coreutils); -f %m is the BSD/macOS equivalent.
    mtime="$(stat -c %Y "$CACHE_FILE" 2>/dev/null || stat -f %m "$CACHE_FILE" 2>/dev/null || printf '0')"
    now="$(date +%s)"
    age=$(( now - mtime ))
    if [ "$age" -lt "$TTL_SECONDS" ]; then
        need_refresh=0
    fi
fi

if [ "$need_refresh" -eq 0 ]; then
    exit 0
fi

# Guard: marketplace clone must exist and be a git work tree with a fetchable
# origin. If any of these fail we just exit quietly; the cache will be absent
# and next session we'll retry.
[ -d "$MARKETPLACE_DIR/.git" ] || exit 0
git -C "$MARKETPLACE_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
git -C "$MARKETPLACE_DIR" remote get-url origin >/dev/null 2>&1 || exit 0

mkdir -p "$CACHE_DIR" 2>/dev/null || exit 0

# Spawn the background refresh. We use a subshell + nohup + disown so the
# detached process survives the parent exiting. All of its own output goes to
# /dev/null — we don't want stray messages in the Claude Code session.
(
    nohup bash -c '
        set -u
        CACHE_FILE="'"$CACHE_FILE"'"
        MARKETPLACE_DIR="'"$MARKETPLACE_DIR"'"

        # Best-effort fetch. --quiet suppresses progress output; --no-tags avoids
        # pulling tag history we do not care about; --prune keeps refs tidy.
        if ! git -C "$MARKETPLACE_DIR" fetch --quiet --no-tags --prune origin >/dev/null 2>&1; then
            # Offline or auth problem — do not touch the cache. Next session retries.
            exit 0
        fi

        local_sha="$(git -C "$MARKETPLACE_DIR" rev-parse HEAD 2>/dev/null)" || exit 0

        # Figure out the upstream ref. Prefer the configured upstream of the
        # current branch; fall back to origin/HEAD (symbolic ref); fall back to
        # origin/master or origin/main in that order.
        remote_ref=""
        if upstream="$(git -C "$MARKETPLACE_DIR" rev-parse --abbrev-ref --symbolic-full-name @{upstream} 2>/dev/null)"; then
            remote_ref="$upstream"
        elif head_ref="$(git -C "$MARKETPLACE_DIR" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null)"; then
            remote_ref="$head_ref"
        elif git -C "$MARKETPLACE_DIR" rev-parse --verify --quiet origin/master >/dev/null 2>&1; then
            remote_ref="origin/master"
        elif git -C "$MARKETPLACE_DIR" rev-parse --verify --quiet origin/main >/dev/null 2>&1; then
            remote_ref="origin/main"
        else
            exit 0
        fi

        remote_sha="$(git -C "$MARKETPLACE_DIR" rev-parse "$remote_ref" 2>/dev/null)" || exit 0

        if [ "$local_sha" = "$remote_sha" ]; then
            update_available="false"
            commits_ahead=0
        else
            update_available="true"
            # Count how many commits on the remote are not in local. If local is
            # ahead (dev branch), this is 0 — treat as no update.
            commits_ahead="$(git -C "$MARKETPLACE_DIR" rev-list --count "$local_sha..$remote_sha" 2>/dev/null || printf 0)"
            if [ "$commits_ahead" = "0" ]; then
                update_available="false"
            fi
        fi

        now_epoch="$(date +%s)"

        # Write cache atomically: write to tmp then rename.
        tmp="${CACHE_FILE}.tmp.$$"
        cat > "$tmp" <<EOF
{
  "update_available": $update_available,
  "local_sha": "$local_sha",
  "remote_sha": "$remote_sha",
  "remote_ref": "$remote_ref",
  "commits_ahead": $commits_ahead,
  "checked": $now_epoch
}
EOF
        mv "$tmp" "$CACHE_FILE" 2>/dev/null || rm -f "$tmp"
    ' >/dev/null 2>&1 &
) >/dev/null 2>&1
disown 2>/dev/null || true

exit 0
