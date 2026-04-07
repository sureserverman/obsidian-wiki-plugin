---
description: Re-scan the current project and rewrite the vault-context sidecar
---

Use the `vault-link-project` skill to re-scan the current project, re-match against
`<vault>/index.md`, and rewrite `<project>/.claude/vault-context.md` in place. The
delimited block in project `CLAUDE.md` is not touched (the import points at the same
sidecar path either way).

**Arguments**: none.

Use this after the vault has been updated (new ingests, lint fixes, schema changes)
and you've re-run `/obsidian-wiki:index` from the vault. Refreshing here picks up the
new index without manually re-running `/vault-context:link`.

This command **only writes** `<project>/.claude/vault-context.md`. The vault is never
modified, and the surrounding content of project `CLAUDE.md` is left alone.

**Examples**:
- `/vault-context:refresh` — re-scan and rewrite the sidecar
