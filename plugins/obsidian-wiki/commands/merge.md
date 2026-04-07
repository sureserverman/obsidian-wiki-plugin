---
description: Merge two vault pages into one and rewrite all inbound wikilinks
---

Use the `vault-merge` skill to merge two pages in `~/dev/knowledge` into a single
canonical page, rewrite every inbound `[[wikilink]]`, remove the loser's row from
`Home.md`, and delete the loser file.

**Arguments**: `$ARGUMENTS` — two paths separated by a space: `<loser> <survivor>`.

If only one path is given, ask for the second. If neither is given, ask for both.

The skill is **destructive**. It always shows a merge plan first and confirms each
phase (content merge, link rewrites, deletion, `Home.md` update) before applying.

**Examples**:
- `/obsidian-wiki:merge Gotchas/old-name.md Gotchas/canonical-name.md`
