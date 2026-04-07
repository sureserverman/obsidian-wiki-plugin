---
description: List vault pages by tag (Dataview-style frontmatter filter)
---

Filter pages in `~/dev/knowledge` by their frontmatter `tags:` field.

Tag(s) to filter on: $ARGUMENTS

## Procedure

1. If `$ARGUMENTS` is empty, scan every page's frontmatter, collect all unique tags,
   and show a tag cloud (each tag with its page count). Stop there.
2. Otherwise, parse `$ARGUMENTS` as one or more tags (space-separated). Find every
   page whose frontmatter `tags:` array contains **all** specified tags (AND
   semantics). Case-insensitive match.
3. Print the matching pages grouped by category directory, with each page's `title:`
   from frontmatter (fall back to filename).

## Special arguments

- `--moc <tag>` — generate a Markdown table that could be added to `Home.md` as a
  new section. Show it; do not write it. The user copies it manually if they want it
  in the index.
- `--count` — just print the count, no listing.

## What never to do

- Do not modify any page's frontmatter.
- Do not modify `Home.md` automatically — only show the proposed table when
  `--moc` is used.

This is a read-only filter. For finding entities that lack a page entirely, use
`/vault-gaps` instead.
