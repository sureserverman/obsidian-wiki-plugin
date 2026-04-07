---
description: Ingest a source from raw/ into the Obsidian vault
---

Use the `vault-ingest` skill to process a source into the wiki at `~/dev/knowledge`.

**Arguments**: `$ARGUMENTS` — path to a file under `~/dev/knowledge/raw/`.

If `$ARGUMENTS` is empty, list files under `~/dev/knowledge/raw/` and ask which one
to ingest.

**Examples**:
- `/obsidian-wiki:ingest raw/article.md` — ingest one specific file
- `/obsidian-wiki:ingest` — list `raw/` and pick interactively
