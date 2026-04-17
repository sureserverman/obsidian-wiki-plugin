---
name: vault-ingest
description: >
  Use when the user asks to ingest a source into their Obsidian vault at <vault>,
  add an article/PDF/page to the wiki, process something dropped into raw/, or mentions
  "/obsidian-wiki:ingest". Trigger on "ingest this", "add this to my notes", "process this article",
  "put this in the wiki", or when a new file appears under <vault>/raw/.
---

> **Vault path:** `<vault>` refers to the path returned by `$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh`. Run it first to resolve the vault location.

# Vault Ingest

Incorporate a new source into the Obsidian vault at `<vault>` by writing or
updating a wiki page, adding cross-references to related pages, and logging the activity.

The vault already has its own structure — do not restructure it. Work within the existing
six category directories and use `Home.md` as the navigation index.

## Preconditions

Before ingesting anything, confirm these exist:

- `<vault>/` — the vault root
- `<vault>/CLAUDE.md` — schema with category rules and frontmatter template
- `<vault>/log.md` — append-only activity log
- `<vault>/raw/` — source inbox

If any are missing, the vault has not been bootstrapped for this plugin. Point the user
at the plugin README (bootstrap section) instead of creating these files yourself.

Read `CLAUDE.md` once per session before the first ingest. It defines the decision rules
for category placement, the frontmatter schema, and the cross-reference conventions that
this vault uses. Trust it over your own defaults.

## Source placement

Sources belong in `raw/`. If the user hands over a path outside `raw/` (a download in
`~/Downloads`, a URL, a paste), offer to copy or save it into `raw/` first and use that
as the canonical source path for citations. This matters because the summary page's
`sources:` frontmatter and the log entry both cite `raw/<filename>`, and those references
need to keep resolving later.

For URLs or clipped web content, save the rendered markdown into `raw/` with a
descriptive filename (date prefix optional). For PDFs or images, keep the binary in
`raw/` and reference it by filename.

## Category selection

The existing wiki uses six top-level directories. Pick exactly one:

| Directory | What goes here |
|---|---|
| `Architecture/` | System-level designs spanning multiple components |
| `Gotchas/` | Surprises, footguns, non-obvious failure modes you want to remember |
| `Patterns/` | Reusable approaches and conventions |
| `Platforms/` | Platform-specific notes (macOS, Linux, Android, etc.) |
| `Projects/` | Per-project notes (one file per project) |
| `Technologies/` | Per-tool / per-protocol notes (one file per technology) |

Read `CLAUDE.md` for the tie-breaker rules when a source could fit in more than one
category. When in doubt, ask the user — do not guess silently.

**Prefer updating over creating.** Before writing a new page, grep the target category
for an existing page on the same topic. If one exists and the source extends it, update
the existing page instead. Creating a parallel page fragments the wiki.

## Summary page

Write the page using the frontmatter schema from `CLAUDE.md`. At minimum:

```yaml
---
title: <Page Title>
aliases: []
tags: [<topic>, <subtopic>]
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
sources: [raw/<filename>]
related: [[Other Page]]
---
```

Body structure (short, readable, grep-friendly):

1. **TL;DR** — 1–3 sentences, the single most important takeaway.
2. **Key points** — bullets, one fact per bullet, each self-contained.
3. **Details** — only the material the source added that wasn't obvious from the key
   points.
4. **Sources** — explicit list of the files/URLs this page draws from, pointing into
   `raw/`.

Do not paraphrase the entire source. The wiki is summary + cross-ref, not a mirror.

## Cross-references

After writing the summary page, scan the rest of the vault for entities the source
mentions. Use grep over the category directories for exact entity names (tool names,
protocol names, project names, platform names).

For each hit:

- **Add a backlink only if the source contributes new information to that page.** A
  pure name-drop does not justify an edit. If the source just says "X uses Tor" and the
  Tor page already knows this, skip it.
- When adding a backlink, insert it where it belongs topically, not at the end of the
  file. Obsidian users care about where links appear.
- Use `[[Page Name]]` link format (Obsidian wikilinks).

If the source contradicts an existing page, do **not** silently overwrite. Surface the
contradiction: add a "Conflicts with" note to the new page, and ask the user how to
reconcile. See the "Contradictions" section below.

## Index update

`Home.md` is the vault's Map-of-Content index. It contains tables organized by
category. If you created a brand-new page in a category that has a table in `Home.md`,
add one row for the new page.

Rules:

- Add only. Never reorder, rename, or remove rows.
- Match the style of surrounding rows exactly (same column count, same link format).
- If the relevant table does not exist in `Home.md`, do not invent one — just skip the
  index update and note it in the report.

## Log append

Append a new entry to `<vault>/log.md`. Newest at the bottom, never edit past
entries. Format:

```
## [YYYY-MM-DD] ingest | <source title>
- Created: [[New Page]]
- Updated: [[Page A]], [[Page B]]
- Cross-refs: [[Page C]]
- Source: raw/<filename>
```

Use today's date. Omit the lines that don't apply (e.g. no "Created" line if you only
updated existing pages).

## Report to user

After all edits, print a compact summary:

- Which page was created or updated (as a path)
- Which pages got new backlinks
- Whether `Home.md` was touched
- Whether any contradiction was flagged
- The log line that was appended

Keep this short — the user will review the diffs in Obsidian.

## Contradictions

If the source disagrees with something already in the vault:

1. Do **not** edit the old page.
2. In the new page, add a `## Conflicts` section that quotes both claims and cites both
   pages.
3. Stop and tell the user. Let them decide whether to update the old page, retire it,
   or keep both.

Silent overwrites destroy wiki history. The user relies on the vault being
append-mostly, and needs to see conflicts explicitly.

## Delegation (optional, for cost/speed)

The summary-page drafting (frontmatter + TL;DR + key points + details sections
from the source content) is a content-transformation job that a Sonnet-tier
worker handles well at lower cost than the caller. If you are on Opus, delegate
the page authoring to the `vault-writer` subagent (model: sonnet) via the Agent
tool with `subagent_type: vault-writer`. Give it:

- the vault path and chosen category dir,
- the source path (under `raw/`),
- the suggested title,
- the frontmatter schema from `CLAUDE.md` (so it matches the vault's conventions),
- any existing page you want updated rather than created anew.

Keep the category decision, the "update vs create" lookup, the cross-reference
pass, the Home.md row, the log append, and any contradiction flagging in this
session — those are the judgment calls and structural edits the vault hinges on.

## Common pitfalls

- **Writing a new page when an existing one would do.** Grep first.
- **Fabricating entities.** Only add cross-refs for entities actually named in the
  source.
- **Name-drop backlinks.** A backlink that doesn't carry new information is noise.
- **Skipping the log append.** The log is what makes the wiki auditable.
- **Rewriting contradictory pages.** Flag, don't overwrite.
- **Modifying `Home.md` beyond adding a row.** The index is hand-curated and fragile.
- **Writing without reading `CLAUDE.md` first.** The schema has decisions baked in
  that are not obvious from the folder names alone.
