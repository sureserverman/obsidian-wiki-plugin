#!/usr/bin/env bash
# check-update.sh — SessionStart hook for obsidian-wiki.
#
# Two responsibilities, both fast and non-blocking:
#
#   1. SYNC: if /tmp/claude/obsidian-wiki-update-check.json says an update is
#      available, print a one-line nudge to stdout. Claude Code surfaces stdout
#      from SessionStart hooks as a session message.
#
#   2. ASYNC: if the cache is missing or older than TTL (6h), spawn a detached
#      background process that does `git fetch` in the marketplace clone,
#      compares HEAD vs origin/HEAD, and rewrites the cache file. The current
#      session never waits on the network.
#
# The script exits silently under any of these conditions (no nudge, no noise):
#   - marketplace clone doesn't exist at ~/.claude/plugins/marketplaces/obsidian-wiki
#   - that directory isn't a git work tree
#   - no `origin` remote, or no upstream set
#   - jq not available and cache parsing fails
#   - fetch fails (offline, auth problem, etc.)
#
# The script NEVER modifies any plugin, marketplace, or user file. It only
# writes its own cache file under /tmp/claude/.

set -u  # fail on undefined vars, but NOT -e — we want best-effort behavior

CACHE_DIR="/tmp/claude"
CACHE_FILE="$CACHE_DIR/obsidian-wiki-update-check.json"
MARKETPLACE_DIR="$HOME/.claude/plugins/marketplaces/obsidian-wiki"
TTL_SECONDS=21600  # 6 hours

# ---------------------------------------------------------------------------
# Part 1 (SYNC): read the cache and maybe print a nudge.
# We only print if the cache exists AND is valid AND says update_available=true.
# Any parse/read failure is silent.
# ---------------------------------------------------------------------------
if [ -f "$CACHE_FILE" ]; then
    # Prefer jq if available for robust parsing; fall back to python3.
    if command -v jq >/dev/null 2>&1; then
        update_available="$(jq -r '.update_available // false' "$CACHE_FILE" 2>/dev/null || printf 'false')"
        commits_ahead="$(jq -r '.commits_ahead // 0' "$CACHE_FILE" 2>/dev/null || printf '0')"
    elif command -v python3 >/dev/null 2>&1; then
        read -r update_available commits_ahead < <(
            python3 -c "
import json, sys
try:
    d = json.load(open('$CACHE_FILE'))
    print(str(d.get('update_available', False)).lower(), d.get('commits_ahead', 0))
except Exception:
    print('false 0')
" 2>/dev/null || printf 'false 0\n'
        )
    else
        update_available="false"
        commits_ahead="0"
    fi

    if [ "$update_available" = "true" ]; then
        # Print the nudge. Pluralize "commit" correctly.
        if [ "$commits_ahead" = "1" ]; then
            printf '[obsidian-wiki] Update available: 1 commit behind. Run `/obsidian-wiki:update` to see what is new.\n'
        else
            printf '[obsidian-wiki] Update available: %s commits behind. Run `/obsidian-wiki:update` to see what is new.\n' "$commits_ahead"
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Part 2 (ASYNC): decide whether to refresh the cache in the background.
# Skip refresh if cache is fresh (< TTL) — otherwise spawn a detached fetch.
# ---------------------------------------------------------------------------
need_refresh=1
if [ -f "$CACHE_FILE" ]; then
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
