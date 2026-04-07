---
name: vault-gaps
description: >
  Use when the user asks to find content gaps in their Obsidian vault, missing pages,
  topics that should have a dedicated note, or mentions "/obsidian-wiki:gaps". Trigger on
  "what's missing from my wiki", "find topics I should write up", "any gaps in my
  notes", or "entities I keep mentioning but don't have a page for".
---

# Vault Gaps

Find topics or entities mentioned across multiple pages in `~/dev/knowledge` that
**don't have a dedicated page** of their own. These are the wiki's content gaps —
candidates for new pages to write.

This is **report-only**. The skill never creates new pages on its own; it only surfaces
candidates and lets the user decide which to write up (using `vault-ingest` once they
have a source).

## Step 1 — Build the entity universe

Scan the six category directories for capitalized names that look like entities. The
heuristic:

- Multi-word `Title Case` runs in prose: "Tor Bootstrap", "Caddy ACME", "GrapheneOS
  Sandbox".
- Quoted commands and tool names: `mkp224o`, `obfs4`, `passwall2`.
- `[[wikilinks]]` whose target file does **not** exist (these are explicit gaps).

Collect each unique entity and the set of pages where it appears.

Exclude:

- Common English title-cased words ("The", "This", "When", section headers).
- Page filenames themselves (a page is not a gap for its own topic).
- Anything inside a code fence — code is reference material, not topic mentions.

## Step 2 — Count and rank

For each entity, count how many distinct pages mention it. Rank by mention count,
descending.

The signal you want: an entity mentioned by ≥3 different pages but lacking its own
dedicated page is almost certainly a gap. An entity mentioned in 1 page is probably
just a passing reference.

## Step 3 — Filter out entities that already have pages

For each candidate entity, check whether a page already exists for it:

- A file in any category directory whose basename matches (case-insensitive).
- A page whose `aliases:` frontmatter includes the entity name.
- A page whose `title:` frontmatter is the entity name.

Remove all matches. The remaining set is the gap candidate list.

## Step 4 — Categorize the gaps

For each gap candidate, suggest where the new page would live (Architecture / Gotchas
/ Patterns / Platforms / Projects / Technologies). Use the rules in `CLAUDE.md` —
when in doubt, look at where the entity is currently mentioned and infer the category
from the surrounding pages.

## Step 5 — Report

```markdown
# Vault gaps — <YYYY-MM-DD>

## High-confidence gaps (mentioned by ≥3 pages, no dedicated page)
1. **Caddy ACME** — likely category: `Technologies/`
   - Mentioned in: `Gotchas/Caddy Let's Encrypt Rate Limits.md`, `Architecture/...`, `Patterns/...`
   - Suggested file: `Technologies/Caddy ACME.md`
2. **GrapheneOS Sandbox** — likely category: `Platforms/`
   - Mentioned in: ...

## Broken wikilinks (already-explicit gaps)
- `[[Hardened Kernel]]` referenced from `Gotchas/...` — no page exists
- ...

## Lower-confidence (mentioned by 2 pages)
- ...
```

Sort by mention count, highest first. Cap each section at 15 entries to keep the
report scannable.

## Step 6 — Log

Append a single one-line entry to `log.md`:

```
## [YYYY-MM-DD] gaps | <H high-confidence, B broken-link, L low-confidence>
```

(Type `gaps` is acceptable as an extension to the standard `ingest|query|lint|schema`
set. The schema's log section should permit it; if `CLAUDE.md` doesn't yet, mention
this to the user as a candidate schema update.)

The report itself is printed to chat, not written into the vault.

## What never to do

- **Auto-create pages.** This skill only surfaces gaps. Use `vault-ingest` to actually
  write a page once a source exists.
- **Suggest gaps that are name-drops.** A capitalized word in one paragraph of one
  page is not a gap.
- **Trust the heuristic blindly.** The user's judgment is the real filter.

## Common pitfalls

- Reporting too many gaps. Cap each section. Quality over quantity.
- Missing aliases — an entity might be covered by a page with a different filename
  but the alias matches. Always check `aliases:` frontmatter.
- Confusing "no page yet" with "no `raw/` source yet". This skill doesn't know whether
  the user has source material — it just reports the gap.
