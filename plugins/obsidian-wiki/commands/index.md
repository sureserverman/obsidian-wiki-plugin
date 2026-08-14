---
description: Regenerate the vault-wide index file at <vault>/index.md
allowed-tools: Bash(python3:*), Read, Write, Edit, Glob, Grep
---

**Run the builder here, in the command, then invoke the skill.** Extraction is
deterministic and belongs in the script, not in the model:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/build-index.py" --vault "<vault>"
```

Then use the `index` skill to review what it produced, resolve anything the script
flagged, and report. The skill holds no shell grant: a command runs only when the
user types it, while a skill can be triggered by natural language, so the one
interpreter call stays at the command layer.

**Arguments**: none.

If the vault is not the current working directory, the skill resolves the vault path
via `${CLAUDE_PLUGIN_ROOT}/scripts/resolve-vault.sh` (env var → config file → fallback).

The index is **derived data** — every run is a full rewrite, so the file is safe to
regenerate as often as you want. The skill skips the write entirely if the new index
is byte-identical to the old one. Other tools (notably the `vault-context` plugin used
from project repos) read this file as the vault's table of contents.

**Examples**:
- `/obsidian-wiki:index` — regenerate `<vault>/index.md` and append a log entry
