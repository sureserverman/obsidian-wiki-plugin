---
description: Show recent activity from the Obsidian vault log
---

`<vault>` is the vault path resolved by `$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh`.


Read `<vault>/log.md` and summarize recent activity. No skill is needed —
this command reads and groups directly.

**Arguments**: `$ARGUMENTS` — number of entries to show (default: `10`).

## Procedure

1. Read `<vault>/log.md`. Each entry starts with `## [YYYY-MM-DD] <type> | <title>`.
2. Take the last N entries (default 10, or `$ARGUMENTS` if it parses as a positive integer).
3. Group them by type (`ingest`, `query`, `lint`, `schema`, `merge`, `gaps`,
   `session-import`).
4. Print the grouped list, then summarize the recent activity in 2–3 sentences.

This is a **read-only** command. Do not modify `log.md`.

**Examples**:
- `/obsidian-wiki:log` — last 10 entries
- `/obsidian-wiki:log 25` — last 25 entries
