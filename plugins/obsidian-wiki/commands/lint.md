---
description: Run a health check over the Obsidian vault
---

Use the `vault-lint` skill to scan `~/dev/knowledge` for orphans, broken wikilinks,
missing frontmatter, possible contradictions, and possibly stale pages.

**Arguments**: `$ARGUMENTS` — `fix` to enter fix mode (default: report-only).

If `$ARGUMENTS` is empty or anything other than `fix`, the skill runs in **report-only**
mode and never edits a file. In `fix` mode it confirms each edit individually.

**Examples**:
- `/obsidian-wiki:lint` — read-only health report
- `/obsidian-wiki:lint fix` — interactive fix mode
