---
description: Run a health check over the Obsidian vault
allowed-tools: Bash(bash:*), Read, Grep, Glob, Edit
---

`<vault>` is the vault path resolved by `$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh`.


**Run the validator first, here in the command, then invoke the skill with its
output.** The mechanical checks — orphans, broken wikilinks, missing frontmatter —
come from the deterministic validator:

```bash
bash "$CLAUDE_PLUGIN_ROOT/scripts/validate.sh" "<vault>" --json
```

Hand that JSON to the `lint` skill, which adds the judgment layer: possible
contradictions and possibly stale pages.

The shell grant lives here rather than in the skill deliberately. A skill can be
triggered by natural language — including text that reached the model from an
ingested source — whereas a command runs only when the user types it. Keeping the
one shell call at the command layer means the grant is live only on explicit user
action. See the skill's own note.

**Arguments**: `$ARGUMENTS` — `fix` to enter fix mode (default: report-only).

If `$ARGUMENTS` is empty or anything other than `fix`, the skill runs in **report-only**
mode and never edits a file. In `fix` mode it confirms each edit individually.

**Examples**:
- `/obsidian-wiki:lint` — read-only health report
- `/obsidian-wiki:lint fix` — interactive fix mode
