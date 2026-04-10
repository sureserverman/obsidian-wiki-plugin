---
description: List vault pages by tag
---

`<vault>` is the vault path resolved by `$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh`.


Filter pages in `<vault>` by their frontmatter `tags:` field (Dataview-style
AND semantics). No skill is needed — this command runs the filter directly.

**Arguments**: `$ARGUMENTS` — one or more tag names, space-separated.

## Procedure

1. If `$ARGUMENTS` is empty, scan every page's frontmatter, collect all unique tags,
   and show a tag cloud (each tag with its page count). Stop there.
2. Otherwise, parse `$ARGUMENTS` as one or more tags. Find every page whose frontmatter
   `tags:` array contains **all** specified tags (AND semantics, case-insensitive).
3. Print matching pages grouped by category directory, with each page's `title:` from
   frontmatter (fall back to filename).

## Special arguments

- `--moc <tag>` — generate a Markdown table that could be added to `Home.md` as a new
  section. Show it; do not write it.
- `--count` — print only the count, no listing.

This is a **read-only** command. Do not modify any page's frontmatter or `Home.md`.

**Examples**:
- `/obsidian-wiki:tag` — tag cloud of every tag
- `/obsidian-wiki:tag tor dns` — pages tagged both `tor` AND `dns`
- `/obsidian-wiki:tag --moc tor` — propose a `tor` MOC table
- `/obsidian-wiki:tag --count tor` — count of pages tagged `tor`
