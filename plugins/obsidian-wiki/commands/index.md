---
description: Regenerate the vault-wide index file at <vault>/index.md
---

Use the `index` skill to walk the Obsidian vault and write a fresh `<vault>/index.md`
listing every page's title, tags, topics, one-line summary, and last-updated date.

**Arguments**: none.

If the vault is not the current working directory, the skill resolves the vault path
via `${CLAUDE_PLUGIN_ROOT}/scripts/resolve-vault.sh` (env var → config file → fallback).

The index is **derived data** — every run is a full rewrite, so the file is safe to
regenerate as often as you want. The skill skips the write entirely if the new index
is byte-identical to the old one. Other tools (notably the `vault-context` plugin used
from project repos) read this file as the vault's table of contents.

**Examples**:
- `/obsidian-wiki:index` — regenerate `<vault>/index.md` and append a log entry
