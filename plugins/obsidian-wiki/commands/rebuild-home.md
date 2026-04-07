---
description: Refresh Home.md tables to match files on disk
---

Use the `vault-home-rebuild` skill to regenerate the tables in `~/dev/knowledge/Home.md`
from the actual filesystem state. This catches drift caused by manual page additions,
renames, or deletions in Obsidian.

**Arguments**: none.

The skill produces a diff first and waits for confirmation per category before applying
any change. The narrative sections of `Home.md` are never touched — only the tables.

**Examples**:
- `/obsidian-wiki:rebuild-home`
