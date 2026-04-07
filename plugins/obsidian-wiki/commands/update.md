---
description: Check for obsidian-wiki marketplace updates and install them
---

Check the `obsidian-wiki` marketplace for upstream updates, show the user what
has changed, and apply the update with confirmation. This command reads the
cache written by the SessionStart hook (`scripts/check-update.sh`); if that
cache is missing or stale, the command runs the check synchronously.

**Arguments**: none.

The command touches only the marketplace clone (via `git` and the `claude`
CLI) and its own cache file at `/tmp/claude/obsidian-wiki-update-check.json`.
It never modifies the user's vault, project files, or any other state.

## Procedure

### 1. Resolve paths

The marketplace clone lives at `~/.claude/plugins/marketplaces/obsidian-wiki`
and the cache file at `/tmp/claude/obsidian-wiki-update-check.json`. If the
marketplace directory does not exist, or is not a git work tree, report
`obsidian-wiki marketplace is not installed as a git clone; nothing to check`
and exit — this can happen if the user added the marketplace from a local
path instead of a GitHub source.

### 2. Get the current update state

Prefer the cached result over running `git fetch` again:

- If `/tmp/claude/obsidian-wiki-update-check.json` exists AND its mtime is
  less than 6 hours old, parse it (it has `update_available`, `local_sha`,
  `remote_sha`, `remote_ref`, `commits_ahead`, `checked`).
- Otherwise, run the checker script synchronously this time — but not via
  the hook's background spawn. Instead, run the same git commands inline:

  ```bash
  git -C ~/.claude/plugins/marketplaces/obsidian-wiki fetch --quiet --no-tags --prune origin
  local_sha=$(git -C ~/.claude/plugins/marketplaces/obsidian-wiki rev-parse HEAD)
  remote_ref=$(git -C ~/.claude/plugins/marketplaces/obsidian-wiki rev-parse --abbrev-ref --symbolic-full-name @{upstream} 2>/dev/null \
               || git -C ~/.claude/plugins/marketplaces/obsidian-wiki symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null \
               || echo origin/master)
  remote_sha=$(git -C ~/.claude/plugins/marketplaces/obsidian-wiki rev-parse "$remote_ref")
  commits_ahead=$(git -C ~/.claude/plugins/marketplaces/obsidian-wiki rev-list --count "$local_sha..$remote_sha")
  ```

  If the fetch fails (offline, auth, etc.), report `Could not fetch from
  upstream — check your network connection and try again.` and exit.

### 3. Already up to date?

If `local_sha == remote_sha` OR `commits_ahead == 0`:

```
## obsidian-wiki Marketplace

Local:  <local_sha:0:7>
Remote: <remote_sha:0:7>

You are already on the latest version.
```

Exit.

### 4. Show the changelog

Run `git log` to get the commits the user does not yet have, formatted as a
compact changelog:

```bash
git -C ~/.claude/plugins/marketplaces/obsidian-wiki log \
    "$local_sha..$remote_sha" \
    --no-decorate --no-merges \
    --pretty=format:'%h %s'
```

Display the result in a framed block, one line per commit. If more than 15
commits are pending, show the 15 most recent and a `... and N more` line.

```
## obsidian-wiki Marketplace Update

Local:   <local_sha:0:7>
Remote:  <remote_sha:0:7>  (<commits_ahead> commits behind)

### What's new

a1b2c3d add /obsidian-wiki:update command
e4f5g6h vault-context: fix sidecar refresh edge case
i7j8k9l docs: clarify vault bootstrap step
```

### 5. Confirm

Use `AskUserQuestion` with a single question:

```
Question: Apply the update?
Options:
  - "Yes, update now"
  - "No, cancel"
```

If the user cancels, report `Update cancelled. Nothing has been changed.`
and exit.

### 6. Run the update

This step shells out to the `claude` CLI — the same binary that is running
this session. The `claude plugin` admin commands are non-interactive and
safe to invoke from inside a running Claude Code session. After each call,
check the exit code; on failure, report the error and stop before attempting
the next step.

```bash
claude plugin marketplace update obsidian-wiki
```

Then, read `~/.claude/plugins/installed_plugins.json` and find every plugin
key ending in `@obsidian-wiki` (i.e. installed from this marketplace). For
each, run:

```bash
claude plugin update <plugin-key>
```

For example, if both are installed:

```bash
claude plugin update obsidian-wiki@obsidian-wiki
claude plugin update vault-context@obsidian-wiki
```

If no plugins from this marketplace are installed, just updating the
marketplace itself is sufficient — skip the per-plugin updates and
report that.

### 7. Clear the cache

```bash
rm -f /tmp/claude/obsidian-wiki-update-check.json
```

This prevents the SessionStart hook from showing a stale "update available"
nudge in the next session, and clears the statusline badge for users who
have installed the snippet.

### 8. Report completion and restart reminder

```
## obsidian-wiki Updated

Local:   <new local_sha:0:7>
Updated: <remote_sha:0:7>
Plugins: obsidian-wiki@obsidian-wiki, vault-context@obsidian-wiki

Restart Claude Code (`/exit` then reopen) to load the new version. The
running session still has the old plugin files loaded.
```

Claude Code's `claude plugin update` help text explicitly says "restart
required to apply", so always show the reminder even though `/reload-plugins`
*might* also work — do not promise that it will.

**Examples**:

- `/obsidian-wiki:update` — check for updates and apply with confirmation
