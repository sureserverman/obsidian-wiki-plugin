---
description: Query the Obsidian vault with citations
---

Use the `vault-query` skill to answer a question against the wiki at `~/dev/knowledge`.

**Arguments**: `$ARGUMENTS` — the question to answer.

If `$ARGUMENTS` is empty, ask what to look up. The skill reads `Home.md` first as the
index, drills into relevant pages, and cites every claim with `[[Page Name]]`. If the
answer has lasting value, the skill offers to file it back as a new wiki page.

**Examples**:
- `/obsidian-wiki:ask what do I know about Tor DNS leaks`
- `/obsidian-wiki:ask which platforms support obfs4 bridges`
