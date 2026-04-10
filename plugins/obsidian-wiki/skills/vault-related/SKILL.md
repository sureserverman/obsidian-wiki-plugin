---
name: vault-related
description: >
  Use when the user asks to find missing cross-references for a specific page in their
  Obsidian vault, mentions "/obsidian-wiki:related", or asks "what should this page link to" or
  "find related notes for X". Trigger on "missing backlinks", "what's related to this",
  or any request to enrich a single page's wikilinks.
---

> **Vault path:** `<vault>` refers to the path returned by `$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh`. Run it first to resolve the vault location.

# Vault Related

Find pages in `<vault>` that a given target page should link to but doesn't.
This is the cross-reference maintenance work the wiki layer is built for — connecting
related ideas after the fact.

The skill reads one target page, identifies the entities it discusses, scans the rest
of the vault for pages on those entities, and reports candidate `[[wikilinks]]` to add.
**Report only** by default — never edit unless the user confirms each suggestion.

## Step 1 — Read the target page

The target is the page passed as argument (e.g. `Gotchas/DNS Leaks.md`). Read it in
full. Note:

- Its frontmatter `tags`, `aliases`, and existing `related:` list.
- Its existing `[[wikilinks]]` — these are the current relationships.
- Entities it mentions in prose: tools, protocols, projects, platforms, people,
  filenames, command names. Distinguish "discussed" entities (the page has something
  to say about them) from pure name-drops.

## Step 2 — Build the candidate set

For each "discussed" entity from Step 1, search the vault for a page that covers it:

- Grep all six category directories for the entity name.
- Match against page filenames (case-insensitive) and against `aliases:` frontmatter.
- For each candidate page, briefly skim it to confirm it's actually about that entity
  (not just a name-drop in a different page).

If multiple pages match the same entity, prefer the most specific one. For example,
if a page mentions "DNS over TLS" and the vault has both `Technologies/Caddy.md` (which
mentions DoT) and `Gotchas/DNS over TLS Through Xray.md` (about DoT specifically),
suggest the latter.

## Step 3 — Filter out existing links

Remove from the candidate set any page the target already links to with `[[Name]]`.
Also remove any page the target already lists in `related:` frontmatter. The goal is
**missing** cross-refs, not redundant ones.

## Step 4 — Filter out name-drops

A backlink is justified only if linking the two pages would help a future reader
follow a meaningful connection. Drop candidates where:

- The target only mentions the entity in passing (one word in a list).
- The candidate page would be reached more naturally from a different page.
- Adding the link would be circular (target ← → candidate already, just unmarked).

The remaining set is the suggestion list.

## Step 5 — Report

Print a structured report:

```markdown
# Related links for `Gotchas/DNS Leaks.md`

## Suggested cross-refs (N)
1. `[[DNS over TLS Through Xray]]` — both pages discuss the DoT-vs-plain-DNS distinction
2. `[[hardened-unbound]]` — target mentions Unbound resolver behavior; this page is about it
3. ...

## Where to insert
- Add `[[DNS over TLS Through Xray]]` near the paragraph about port 853.
- Add `[[hardened-unbound]]` to the "Sources" section as related reading.
```

For each suggestion, give the candidate page and the **specific paragraph or sentence**
in the target where the link should be inserted. Vague "add somewhere" suggestions are
useless.

## Step 6 — Apply (only on confirmation)

If the user accepts some or all suggestions, edit the target page one suggestion at a
time. Use the Edit tool — never Write the whole file. Confirm before each edit.

After applying, optionally also update the corresponding candidate page's `related:`
frontmatter to mention the target (bidirectional link). Ask first.

## What never to do

- **Auto-apply suggestions.** Always report-only by default.
- **Edit the candidate pages without asking.** The skill is named "related" — its job
  is to enrich the *target*, not rewrite five other pages.
- **Suggest links to `Home.md`.** The index is hand-curated and lives separately.
- **Suggest backlinks for entities the target doesn't actually discuss.** Pure name-drops
  are noise.

## Common pitfalls

- Producing too many suggestions and overwhelming the user. Keep it to ≤10 high-quality
  suggestions per run; if there are more, present the top 10 and offer to show the rest.
- Suggesting wikilinks that point to alias forms not in the target page's frontmatter
  (Obsidian renders them, but the link form should match the canonical filename).
- Skipping the "where to insert" hint. A list of bare suggestions is much less useful
  than a list with paragraph anchors.
