---
name: vault-home-rebuild
description: >
  Use when the user asks to refresh, rebuild, or regenerate Home.md in their Obsidian
  vault, mentions "/obsidian-wiki:rebuild-home", or notices that Home.md has drifted from the
  actual files on disk. Trigger on "rebuild the index", "refresh Home.md", "Home is
  out of date", or "the index is stale".
---

# Vault Home Rebuild

Regenerate the tables in `~/dev/knowledge/Home.md` from the actual filesystem state,
catching drift caused by manual page additions, renames, or deletions in Obsidian.

`Home.md` is a hand-curated Map-of-Content. The `vault-ingest` skill only adds rows
to it; it never removes or reorders. Over time, when the user creates pages directly in
Obsidian (or deletes them), `Home.md` falls out of sync. This skill catches that.

This skill is **destructive** — it rewrites parts of `Home.md`. It always produces a
diff first and waits for confirmation before applying.

## Step 1 — Read current Home.md

Read `Home.md` in full and parse out:

- The non-table sections (introduction, "Overview", "Core themes", any narrative
  paragraphs). These are preserved verbatim.
- Each table: its heading (e.g. "### Infrastructure & Networking"), its columns,
  and its rows. Each row links one or more pages with `[[Name]]`.

The introduction and narrative content are sacred. Only the **table rows** are
candidates for regeneration.

## Step 2 — Inventory the filesystem

For each page file under the six category directories:

- Read the file's frontmatter (`title`, `tags`, optional `summary` or first-line
  description).
- Decide which `Home.md` section the page belongs to. Use the page's category
  directory plus its tags. The current `Home.md` shows the precedent — match it.

Build a target table for each section, sorted to match the existing order convention
(usually alphabetical or grouped by sub-theme).

## Step 3 — Diff against current

For each table, compute:

- **Rows to add**: pages on disk that are not in the current table.
- **Rows to remove**: rows in the current table whose page no longer exists on disk.
- **Rows that changed**: rows where the page exists but its description has drifted
  (e.g. the `Home.md` row says one thing, the page's frontmatter `title` or `summary`
  says another).

Do **not** auto-reorder existing rows. Drift in row order is not a bug — the user
may have ordered rows intentionally.

## Step 4 — Present the diff

Show the user, table by table:

```markdown
## Table: Infrastructure & Networking

### To add (3)
- `[[new-tor-bridge-tool]]` — GPU-accelerated Tor bridge enumeration
- ...

### To remove (1)
- `[[old-deleted-page]]` — page no longer exists on disk

### To change (2)
- `[[caddy]]` — description drift:
  - Home.md says: "Auto-HTTPS web server"
  - Page title says: "Auto-HTTPS web server + reverse proxy (Go)"
```

Per-section, ask: "Apply additions? Remove obsolete rows? Update descriptions?" The
user answers per category, per operation type. Do not batch into one big yes/no.

## Step 5 — Apply (per confirmation)

For each confirmed change, edit `Home.md` with the Edit tool. Edit one row at a time
when possible. Never Write the whole file — Edit only.

Order of operations within a single table:

1. Removals first (so subsequent additions land at the right indices).
2. Description changes second.
3. Additions last, inserted in the correct order to match the surrounding pattern.

## Step 6 — Log

Append to `log.md`:

```
## [YYYY-MM-DD] schema | Rebuilt Home.md
- Added: <list of pages>
- Removed: <list of pages>
- Updated: <list of pages>
- Reason: <one-line, e.g. "manual page additions in Obsidian since last sync">
```

Use type `schema` because `Home.md` is part of the vault's structural layer, even
though `vault-schema-maintain` doesn't touch it. (Alternatively, the user may want to
extend the schema to allow a `home` type — flag this if it comes up repeatedly.)

## What never to do

- **Rewrite `Home.md` wholesale.** Always Edit-by-row.
- **Touch the introduction or narrative sections.** Only tables.
- **Remove rows the user might still want.** Always confirm removals individually.
- **Reorder existing rows.** Order is curated.
- **Fabricate descriptions.** A new row's description must come from the page's
  frontmatter `title` or first-paragraph summary, not from your own paraphrase of the
  body.

## Common pitfalls

- Treating the diff as a script to run automatically — it's a proposal the user
  approves.
- Missing pages whose category placement is ambiguous (e.g. a page tagged both
  `tor` and `gotcha`). Ask the user where it goes.
- Auto-resolving description drift by overwriting the page's frontmatter. The page is
  the source of truth, not `Home.md` — update `Home.md` to match the page, never
  the other way around.
