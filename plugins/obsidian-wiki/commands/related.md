---
description: Find missing cross-references for a vault page
---

Use the `vault-related` skill to find pages in `~/dev/knowledge` that the target page
should link to but doesn't.

**Arguments**: `$ARGUMENTS` — path to the target page.

If `$ARGUMENTS` is empty, ask which page to analyze. The skill is **read-only** — it
suggests cross-refs and waits for confirmation before applying any edit.

**Examples**:
- `/obsidian-wiki:related Gotchas/DNS Leaks.md`
- `/obsidian-wiki:related Technologies/Caddy.md`
