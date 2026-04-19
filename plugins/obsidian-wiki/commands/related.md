---
description: Find missing cross-references for a vault page
---

`<vault>` is the vault path resolved by `$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh`.


Use the `related` skill to find pages in `<vault>` that the target page
should link to but doesn't.

**Arguments**: `$ARGUMENTS` — path to the target page.

If `$ARGUMENTS` is empty, ask which page to analyze. The skill is **read-only** — it
suggests cross-refs and waits for confirmation before applying any edit.

**Examples**:
- `/obsidian-wiki:related Gotchas/DNS Leaks.md`
- `/obsidian-wiki:related Technologies/Caddy.md`
