---
description: Show a dashboard of the Obsidian vault
---

`<vault>` is the vault path resolved by `$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh`.


Produce a vault dashboard for `<vault>`: page counts, hubs, orphans, recent
activity, and possibly stale pages. No skill is needed — this command computes the
report directly from the filesystem and `log.md`.

**Arguments**: `$ARGUMENTS` — `verbose` for per-category breakdowns (default: terse).

## Procedure

1. **Page counts**: count `.md` files in each of the six category dirs (Architecture,
   Gotchas, Patterns, Platforms, Projects, Technologies). Show as a table with totals.
2. **Hub pages (top 10)**: rank pages by inbound `[[wikilink]]` count. Exclude
   `Home.md`.
3. **Orphan count**: count pages with **zero** inbound wikilinks (excluding `Home.md`
   and `raw/`). Show the count and the first 5 examples; point to `/obsidian-wiki:lint` for the
   full list.
4. **Recent activity**: read the last 10 entries from `log.md`, group by type, summarize
   the recent week's activity in 2–3 sentences.
5. **Possibly stale (top 5)**: read frontmatter `updated:` from each page and show the
   5 oldest by `updated:` date.

In `verbose` mode, also show per-category orphan and hub breakdowns.

This is a **read-only** command. Do not modify any vault file.

**Examples**:
- `/obsidian-wiki:stats` — terse dashboard
- `/obsidian-wiki:stats verbose` — with per-category breakdowns
