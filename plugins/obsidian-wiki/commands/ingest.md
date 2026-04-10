---
description: Ingest a source from raw/ into the Obsidian vault
---

`<vault>` is the vault path resolved by `$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh`.


Use the `vault-ingest` skill to process a source into the wiki at `<vault>`.

**Arguments**: `$ARGUMENTS` — path to a file under `<vault>/raw/`.

If `$ARGUMENTS` is empty, list files under `<vault>/raw/` and ask which one
to ingest.

**Examples**:
- `/obsidian-wiki:ingest raw/article.md` — ingest one specific file
- `/obsidian-wiki:ingest` — list `raw/` and pick interactively
