# Vault Schema (CLAUDE.md)

This file is the schema for the Obsidian vault at `~/dev/knowledge`. It tells the
`obsidian-wiki` plugin how this vault is organized and how to operate on it.

This file is **read by every wiki operation** (ingest, query, lint) and is **edited only
by the `vault-schema-maintain` skill**, never in ad-hoc sessions. Edit it surgically — do
not rewrite the whole document.

The schema evolves over time as conventions are corrected. Each change is recorded in
`log.md` with type `schema`.

---

## Vault structure

The vault has six top-level category directories plus a few root-level files:

| Path | Purpose |
|---|---|
| `Architecture/` | System-level designs that span multiple components |
| `Gotchas/` | Surprises, footguns, non-obvious failure modes |
| `Patterns/` | Reusable approaches and conventions |
| `Platforms/` | Per-platform notes (one file per platform) |
| `Projects/` | Per-project notes (one file per project) |
| `Technologies/` | Per-tool / per-protocol notes (one file per technology) |
| `Home.md` | Hand-curated Map-of-Content index. Tables link every wiki page. |
| `log.md` | Append-only activity log (ingest / query / lint / schema entries). |
| `raw/` | Source inbox. Articles, PDFs, clipped pages. Immutable — never edited. |
| `raw/assets/` | Images and binary assets referenced from `raw/`. |
| `raw/sessions/` | Extracted AI coding sessions (Claude Code, Cursor, Codex, Gemini, OpenCode). One markdown file per imported session. |
| `.obsidian/` | Obsidian app config. Do not touch. |

The wiki layer is the six category directories. Everything else is infrastructure.

---

## Page naming

- **Title Case with spaces** is allowed and preferred. Example: `Tor Bootstrap Through VLESS.md`.
- **One topic per file.** If you find yourself wanting to write `X and Y.md`, you
  probably want two files plus cross-links.
- **No date prefixes** in wiki page filenames. Dates live in frontmatter, not filenames.
  Source files in `raw/` may have date prefixes for sorting; wiki pages do not.
- **No subdirectories inside category dirs.** The structure is flat: `Gotchas/X.md`,
  not `Gotchas/networking/X.md`. Use tags for subcategorization.

---

## Frontmatter schema

Every wiki page starts with a YAML frontmatter block:

```yaml
---
title: <Page Title>
aliases: []                # other names this page goes by
tags: [<topic>, <subtopic>]
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
sources: [raw/<filename>]  # files in raw/ this page summarizes
related: [[Other Page]]    # related wiki pages, in [[wikilink]] form
---
```

Required fields: `title`, `created`. Everything else is optional but encouraged.

`updated` is bumped on every edit by the editing skill (never manually). `sources` is
appended to (not replaced) when a new source contributes to an existing page.

---

## Category decision rules

When ingesting a source, pick exactly one category. Tie-breakers in order:

1. **Per-tool / per-protocol info** → `Technologies/`. (Example: a new article about
   how Caddy handles ACME → `Technologies/Caddy.md`.)
2. **Per-platform info** → `Platforms/`. (Example: macOS launchd quirks →
   `Platforms/macOS.md`.)
3. **Per-project info** → `Projects/`. (Example: a design note about the `puliax`
   project → `Projects/puliax.md`.)
4. **Reusable approach across projects/tools** → `Patterns/`. (Example: "how to make
   installer scripts idempotent" → `Patterns/Idempotent Installation.md`.)
5. **A specific surprise or footgun you want to remember** → `Gotchas/`. (Example:
   "WireGuard kill switch breaks DNS through Tor containers" → `Gotchas/`.)
6. **A multi-component system design** → `Architecture/`. (Example: "containerized DNS
   stack of Pi-hole + Unbound + Tor" → `Architecture/`.)

If a source could fit in two categories, pick the more specific one. If still tied,
ask the user.

---

## Ingest procedure (mirrors the `ingest` skill)

This is repeated here so a human can read the procedure without loading the skill.

1. Confirm the source is in `raw/`. If not, copy it in first.
2. Read the source.
3. Pick the category using the rules above.
4. Grep the target category for an existing page on the same topic. **Prefer updating
   over creating.**
5. Write or update the page using the frontmatter schema. Body has TL;DR + Key points
   + Details + Sources.
6. Scan the rest of the vault for entities the source mentions. Add `[[wikilinks]]`
   only where the source contributes new information — not for name-drops.
7. If a brand-new page was created in a category that has a table in `Home.md`, add
   one row. **Add only — never reorder, rename, or remove.**
8. Append a `[YYYY-MM-DD] ingest |` entry to `log.md`.
9. Report the changes to the user.

---

## Cross-reference rules

- A backlink is justified when the source contributes new information to the linked
  page. A pure name-drop is not.
- Use `[[Page Name]]` (Obsidian wikilinks). Aliases via `[[Page Name|alias]]`.
- Insert backlinks topically, not at the end of the file. Position matters in Obsidian.
- If the link would create a contradiction with existing content, **do not silently
  resolve it.** Add a `## Conflicts` section instead, and ask the user.

---

## Home.md update rules

`Home.md` is hand-curated. The plugin may add rows but never reorder, rename, or
remove them.

- **Add only.** Never modify existing rows.
- **Match style.** Same column count, same link format, same row ordering convention
  as the surrounding rows.
- **If the relevant table doesn't exist, skip.** Do not invent new tables in `Home.md`.

---

## log.md format

Append-only. Newest entries at the bottom. Do not edit past entries.

Each entry is a level-2 heading followed by optional bullet detail:

```
## [YYYY-MM-DD] <type> | <title>
- <detail>
- <detail>
```

`<type>` is one of: `ingest`, `query`, `lint`, `schema`, `merge`, `gaps`, `session-import`, `session-capture`, `index`.

`query` entries are only logged when a new page was filed back. Plain queries that
just produced an answer are not logged.

`session-import` entries are appended by the `import-session` skill when an AI
coding session is extracted into `raw/sessions/`. The chained `ingest` (if the
user accepts) produces a separate `ingest` entry.

`session-capture` entries are appended by the `obsidian-wiki` SessionEnd hook
(`scripts/capture-session.sh`) — see the "Auto-capture from SessionEnd" section
below.

---

## Lint criteria (mirrors the `lint` skill)

The lint skill checks five categories:

1. **Orphans** — pages with zero inbound `[[wikilinks]]`. Excludes `Home.md` and
   `raw/`.
2. **Broken wikilinks** — `[[Name]]` references whose target file does not exist.
3. **Missing frontmatter** — pages without a valid YAML frontmatter block containing
   at least `title` and `created`.
4. **Possible contradictions** (heuristic) — pages with overlapping topics that make
   opposing factual claims.
5. **Possibly stale** (heuristic) — pages with `updated:` older than 6 months that
   reference fast-moving software/protocols.

Lint runs in **report-only mode by default.** Fix mode requires explicit user request
and confirms each edit individually.

---

## Session imports

The plugin can extract content from AI coding sessions across five tools (Claude Code,
Codex, Cursor, Gemini, OpenCode) and turn them into vault sources. Two skills are
involved:

- `scan-sessions` — read-only discovery. Finds candidate sessions in the user's
  tool storage dirs, scores them for vault-worthiness, presents a ranked report.
- `import-session` — extracts one chosen session into
  `raw/sessions/<tool>-<YYYY-MM-DD>-<short-id>.md`, then optionally chains to
  `ingest` to file the source into the wiki.

**Filename convention** for extracted sessions:

```
raw/sessions/<tool>-<YYYY-MM-DD>-<short-id>.md
```

Where `<tool>` ∈ `claude-code`, `codex`, `cursor`, `gemini`, `opencode` and
`<short-id>` is the first 8 chars of the session UUID (or project hash for OpenCode).

**Idempotency rule.** A session is "already imported" if either:

1. The file exists at `raw/sessions/<tool>-<date>-<short-id>.md`, OR
2. Some wiki page's `sources:` frontmatter array contains that path.

`scan-sessions` filters out already-imported sessions; `import-session`
refuses to overwrite without `--force`.

The session import skills never read the entire session file into context — they
stream-parse and extract only the substantive turns (assistant explanations, errored
tool results, summaries). Verbose tool input/output is dropped.

---

## Auto-capture from SessionEnd

The `obsidian-wiki` plugin registers a `SessionEnd` hook
(`scripts/capture-session.sh`) that fires when any Claude Code session ends in
any project (anywhere except inside the vault itself). The hook scores the
just-ended session via lightweight heuristics — long sessions, error clusters,
substantive final messages, user-satisfaction markers — and if the score crosses
the threshold (default 2, override with `OBSIDIAN_WIKI_CAPTURE_THRESHOLD=N`),
appends a `session-capture` entry to this log.

The capture entry is **informational only**: the hook never extracts the
session's content. The actual extract still happens via `import-session`
when you run `/obsidian-wiki:review-captures` from within the vault. Captures
are idempotent (a session-id is only ever captured once) and the hook never
writes to `raw/`, the wiki, or anything outside `log.md`.

When `import-session` produces an extract from a capture, it appends a
`Captured-as: [<date>] session-capture <short-id>` line to its `session-import`
log entry. That line is the cross-reference `review-captures` uses to tell
imported captures from pending ones — captures are never edited or deleted, so
the cross-ref on the import entry is the only "this capture has been processed"
marker.

Opt out:
- Per shell: `export OBSIDIAN_WIKI_NO_CAPTURE=1` in your environment.
- Per project: create an empty `.obsidian-wiki-no-capture` file at the project root.

Tune sensitivity with `OBSIDIAN_WIKI_CAPTURE_THRESHOLD=N` (default 2,
practical range 0–6). Lower = more captures.

---

## Vault index

`<vault root>/index.md` is a **derived, machine-readable digest** of every wiki page:
title, path, tags, topic mentions, one-line summary, and last-updated date, grouped by
category. It exists so other tools (notably the `vault-context` plugin used from
project repos) can find vault pages relevant to their context without having to grep
the whole vault.

The index is written **only** by the `index` skill (`/obsidian-wiki:index`).
Hand-edits are pointless — every run is a full rewrite. The skill skips the write if
the new content is byte-identical to the old one, so the file's mtime tracks real
content changes. Index runs append a `[YYYY-MM-DD] index |` entry to `log.md`.

`index.md` is **not** part of the wiki layer. It is excluded from lint orphan
detection, lint broken-link detection, and the index walk itself. Treat it the same
way as `Home.md` — present at the vault root, but not a wiki page.

---

## Schema evolution

This file (`CLAUDE.md`) is edited only by the `vault-schema-maintain` skill. Edits are
surgical — minimal diffs against existing sections, never whole-file rewrites.

Every schema edit:

- Belongs to exactly one section above.
- Is confirmed with the user before applying.
- Produces a `[YYYY-MM-DD] schema |` entry in `log.md` with a `Reason:` line.

If a new rule doesn't fit any existing section, ask the user where to put it before
adding a section. Do not invent sections silently.
