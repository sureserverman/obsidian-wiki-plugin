#!/usr/bin/env bash
# statusline-snippet.sh — a copy-paste snippet you can add to your own
# Claude Code statusline script to show an "update available" badge for the
# obsidian-wiki marketplace.
#
# This file is NOT wired into Claude Code automatically. Claude Code plugins
# cannot directly contribute to the statusline — only one `statusLine.command`
# can be active at a time, and it is owned by your ~/.claude/settings.json.
# To get the badge, paste the snippet below into your statusline script.
#
# The snippet reads the cache file written by the obsidian-wiki SessionStart
# hook (`scripts/check-update.sh`) and appends a badge to your statusline
# output when an update is available. It requires `jq`, which most statusline
# scripts already depend on.
#
# ---------------------------------------------------------------------------
# HOW TO INSTALL
# ---------------------------------------------------------------------------
#
# 1. Find your statusline script. It is the `command` field under `statusLine`
#    in ~/.claude/settings.json. A common location is ~/.claude/statusline.sh.
#
# 2. Paste the snippet below into that script, somewhere AFTER `$out` (or your
#    equivalent output variable) has been built up but BEFORE the final
#    `printf`/`echo` that emits it. If your statusline already uses an `$out`
#    variable and `${sep}` / `${yellow}` / `${dim}` / `${reset}` ANSI color
#    variables (the daniel3303/ClaudeCodeStatusLine convention), the snippet
#    works unmodified. Otherwise adjust the color codes and output variable.
#
# 3. Reload your shell or start a new Claude Code session. The badge will
#    appear whenever the SessionStart hook has flagged an update.
#
# ---------------------------------------------------------------------------
# SNIPPET — copy from here...
# ---------------------------------------------------------------------------

# --- obsidian-wiki update badge ---
# Shows "obsidian-wiki ⬆ N" when the SessionStart hook has detected upstream
# updates. Requires jq. Silent (no badge) when there is no cache file, no
# update, or jq is unavailable.
ow_cache="/tmp/claude/obsidian-wiki-update-check.json"
if [ -f "$ow_cache" ] && command -v jq >/dev/null 2>&1; then
    if jq -e '.update_available == true' "$ow_cache" >/dev/null 2>&1; then
        ow_ahead=$(jq -r '.commits_ahead // 0' "$ow_cache")
        # If your statusline uses different color/output variables, adjust here.
        # These match the daniel3303/ClaudeCodeStatusLine convention.
        out+="${sep:- | }${yellow:-}obsidian-wiki ⬆${reset:-} ${dim:-}${ow_ahead}${reset:-}"
    fi
fi
# --- end obsidian-wiki update badge ---

# ---------------------------------------------------------------------------
# ...to here.
# ---------------------------------------------------------------------------
#
# NOTES
#
# - The `${sep:- | }` / `${yellow:-}` / etc. are "default if unset" expansions.
#   If your statusline script already defines these (most do), you get the
#   styled output. If it does not, you get a plain " | obsidian-wiki ⬆ 3"
#   without colors — still readable, just uglier.
#
# - The cache file is written by the obsidian-wiki SessionStart hook at most
#   once every 6 hours, in the background. It never blocks your statusline.
#
# - To clear the badge immediately after updating, run `/obsidian-wiki:update`.
#   That command removes the cache file on successful update, so the next
#   statusline render will not show the badge.
#
# - If you never want the badge, simply do not paste the snippet. The plugin
#   works fine without it — the SessionStart hook still prints a one-line
#   nudge at session start when updates are available.
