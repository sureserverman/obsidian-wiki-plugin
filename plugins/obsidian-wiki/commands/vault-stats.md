---
description: Show a dashboard of the Obsidian vault at ~/dev/knowledge (page counts, hubs, orphans, recent activity)
---

Produce a vault dashboard for `~/dev/knowledge`. Read what you need from the filesystem
and from `log.md`, then print a structured report:

## Section 1 — Page counts

For each of the six category directories (Architecture, Gotchas, Patterns, Platforms,
Projects, Technologies), count the number of `.md` files. Show as a table with totals.

## Section 2 — Hub pages (top 10)

A "hub" is a page with the most inbound `[[wikilinks]]` from other pages. Grep the
vault for `[[<basename>]]` of each page and rank by inbound count. Show the top 10 with
their counts. Exclude `Home.md`.

## Section 3 — Orphan count

Count pages with **zero** inbound `[[wikilinks]]` (excluding `Home.md` and `raw/`). Show
the count and the first 5 examples. If the user wants the full list, point them at
`/vault-lint`.

## Section 4 — Recent activity

Read the last 10 entries from `log.md`. Group by type (`ingest` / `query` / `lint` /
`schema` / `merge` / `gaps`). Summarize the recent week's activity in 2–3 sentences.

## Section 5 — Possibly stale (top 5)

Read frontmatter `updated:` from each page. Show the 5 oldest pages by `updated:` date.
This is a quick proxy for which pages are most likely out of date.

## Output format

Print one section at a time, with clear headings. Keep numbers prominent. Do not
modify any vault file — this is read-only.

If `$ARGUMENTS` is `verbose`, also show per-category orphan and hub breakdowns.
