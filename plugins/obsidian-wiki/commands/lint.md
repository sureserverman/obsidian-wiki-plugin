---
description: Run a health check over the Obsidian vault
---

`<vault>` is the vault path resolved by `$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh`.


Use the `lint` skill to scan `<vault>` for orphans, broken wikilinks,
missing frontmatter, possible contradictions, and possibly stale pages.

**Arguments**: `$ARGUMENTS` — `fix` to enter fix mode (default: report-only).

If `$ARGUMENTS` is empty or anything other than `fix`, the skill runs in **report-only**
mode and never edits a file. In `fix` mode it confirms each edit individually.

**Examples**:
- `/obsidian-wiki:lint` — read-only health report
- `/obsidian-wiki:lint fix` — interactive fix mode
