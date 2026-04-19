---
name: lint
description: >
  Use when the user asks for a vault health check, mentions "/obsidian-wiki:lint", or asks about orphan
  pages, broken wikilinks, contradictions between notes, stale claims, or missing backlinks
  in their Obsidian vault. Trigger on "lint my vault", "check wiki health", "find orphans",
  or "any broken links in my notes".
---

> **Vault path:** `<vault>` refers to the path returned by `$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh`. Run it first to resolve the vault location.

# Vault Lint

Run a health check over the Obsidian vault at `<vault>` and report problems.

Default mode is **report-only** — never auto-edit the vault during a lint unless the
user explicitly asks for fix mode. The vault is hand-curated and a silent "cleanup" can
destroy user work.

## What to check

The check has five categories. Run each one and collect its findings before reporting.
Do not stop at the first finding.

### 1. Orphan pages

A page is an orphan if no other page in the vault links to it with `[[Name]]`. Excluded
from orphan detection:

- `Home.md` (the index is expected to have no inbound links)
- Anything under `raw/` (sources, not wiki pages)
- Anything under `.obsidian/` (Obsidian internal)

To find orphans: for each `.md` file in the six category directories, grep the rest of
the vault for the file's basename (without extension) inside `[[...]]`. Zero hits = orphan.

Case-insensitive match. Handle `[[Name]]`, `[[Name|alias]]`, and `[[Name#section]]` as
link forms.

### 2. Broken wikilinks

For every `[[target]]` that appears anywhere in the vault, verify a matching file exists
under the six category directories. Match by basename, case-insensitive, with or without
`.md` suffix. Also check for aliases declared in the target file's frontmatter
(`aliases: [...]`).

Report broken links grouped by the file that contains them, so the user can open each
source file once and fix all its broken links together.

### 3. Missing frontmatter

A page is missing frontmatter if it does not start with a `---` block containing at
least `title:` or `tags:`. The schema in `CLAUDE.md` defines the required fields. If
`CLAUDE.md` is not present, treat `title` and `created` as the minimum.

Report only. Never auto-add frontmatter — the user chose the current state intentionally.

### 4. Possible contradictions (heuristic)

This is fuzzy and should be flagged as candidates, not verdicts. Look for:

- Pages sharing a tag or topic that make opposing factual claims about the same thing
  (version numbers, compatibility statements, "does X work with Y").
- Pages where one says "do X" and another says "do not do X".
- Pages whose `updated:` timestamps are very close but whose content disagrees.

Report each candidate as a pair of pages plus the specific sentences that appear to
conflict. Let the user judge.

### 5. Possible stale claims (heuristic)

A claim is possibly stale if:

- The page's `updated:` frontmatter is more than 6 months old, AND
- The page references a fast-moving topic (a specific version of software, a protocol
  status like "experimental", a dated compatibility statement).

Report as candidates. Do not edit.

## Report format

Produce a single markdown report with this structure:

```markdown
# Vault Lint Report — <YYYY-MM-DD>

## Orphans (N)
- `Gotchas/Example Orphan.md`
- ...

## Broken wikilinks (N, in M files)
- In `Architecture/X.md`:
  - `[[Nonexistent Page]]`
- ...

## Missing frontmatter (N)
- `Patterns/Y.md`

## Possible contradictions (N)
- `Gotchas/A.md` vs `Gotchas/B.md`
  - A says: "..."
  - B says: "..."

## Possibly stale (N)
- `Technologies/Z.md` (updated 2025-08-01, references "Xray v1.8 experimental")
```

Include counts in each heading so the user can scan the severity at a glance.

## Log append

After producing the report, append a single entry to `<vault>/log.md`:

```
## [YYYY-MM-DD] lint | <N orphans, M broken, K missing frontmatter, L contradictions, P stale>
```

The log entry is a one-liner. The report itself is printed to the chat, not saved to
`log.md`.

## Fix mode (only on explicit request)

If the user says "fix the orphans" or "add frontmatter" or similar, enter fix mode for
that category only. Fix mode rules:

- Handle one category at a time.
- Confirm each individual edit before making it — do not batch.
- For orphans: the fix is usually either to add a backlink from a relevant page or to
  delete the orphan. The user must decide which.
- For broken links: ask whether the link target should be renamed, created, or the
  broken link removed.
- For missing frontmatter: write only the minimum (`title`, `created` = file mtime,
  `updated` = today). Do not invent tags.
- Never auto-resolve contradictions or stale claims — those always require human
  judgment.

## Delegation (optional, for cost/speed)

Categories 1 and 2 (orphans, broken wikilinks) are read-heavy grep-and-match work.
If the vault is large or the session is running on Opus, delegate those two phases
to the `vault-scanner` subagent (model: haiku). Use the Agent tool with
`subagent_type: vault-scanner` and give it the vault path plus the specific task
(e.g., "return orphan candidates" or "return broken `[[target]]` references grouped
by source file"). Merge the returned findings into your report.

Keep categories 3–5 (frontmatter, contradictions, stale claims) in this session —
they need judgment, not bulk I/O.

## Common pitfalls

- **Running in fix mode by default.** Always report first.
- **Treating heuristics as verdicts.** Contradiction and staleness checks are
  candidates the user validates.
- **Grepping the vault without excluding `raw/` and `.obsidian/`.** That produces
  false-positive broken links and orphans.
- **Auto-deleting orphans.** Never. An orphan might be a page the user is about to
  link from a work-in-progress note.
- **Silently rewriting frontmatter.** Never. The user may have non-standard fields
  intentionally.
