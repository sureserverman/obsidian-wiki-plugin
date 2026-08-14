---
name: lint
allowed-tools: Read, Glob, Grep, Edit
description: >
  Use when the user asks for a vault health check, mentions "/obsidian-wiki:lint", or asks about orphan
  pages, broken wikilinks, contradictions between notes, stale claims, or missing backlinks
  in their Obsidian vault. Trigger on "lint my vault", "check wiki health", "find orphans",
  or "any broken links in my notes".
---

> **This skill holds no shell grant.** The deterministic step runs in the
> `/obsidian-wiki:lint` command, which hands its output here. If you were invoked
> without that output, ask the user to run the command — do not attempt to run the
> script yourself. A command runs only on explicit user action; a skill can be
> triggered by natural language, so the shell call is deliberately kept where an
> injected instruction cannot reach it.


> **Vault path:** `<vault>` is published by the SessionStart hook at
> `${XDG_CONFIG_HOME:-~/.config}/obsidian-wiki/state/vault-path` — **Read** that file;
> do not shell out. If it is missing (hooks disabled, or a first session before the
> hook has run), read `default_vault` from `~/.config/obsidian-wiki/config.json`, and
> fall back to `~/dev/knowledge`. The hook is the only place `$OBSIDIAN_VAULT_PATH` is
> honoured, so reading its output keeps skills and hooks pointed at the same vault.

# Vault Lint

Run a health check over the Obsidian vault at `<vault>` and report problems.

Default mode is **report-only** — never auto-edit the vault during a lint unless the
user explicitly asks for fix mode. The vault is hand-curated and a silent "cleanup" can
destroy user work.

## What to check

A lint has two lanes. The **mechanical lane** — orphans, broken wikilinks, and
malformed frontmatter — is decided by this plugin's deterministic validators in
`scripts/`; you run them and report their findings verbatim. The **judgment lane**
— possible contradictions and possibly-stale claims — needs your reading and stays
below. Collect everything before reporting; do not stop at the first finding.

### Mechanical lane — run the validators (do not re-derive these by hand)

Run the domain validators against the resolved vault and parse their JSON. They
do the grep-and-match that this skill used to describe in prose, identically every
run:

```bash
bash "$CLAUDE_PLUGIN_ROOT/scripts/validate.sh" "<vault>" --json
```

(That runs both `validate-vault.sh` — orphans, broken wikilinks, missing/empty
frontmatter — and `validate-log.sh` — `log.md` drift. Run one directly if you only
need that slice.)

Each finding is `{severity, rule, category, path, line, message}`. The rules:

- `vault-broken-wikilink` (warn) — a `[[target]]` resolving to no page, alias, or
  file (case-insensitive; `#section`/`|alias` suffixes, path-style links into
  `raw/`, fenced code, and escaped table pipes are all handled). To report "grouped
  by source file," just sort the findings by `path`.
- `vault-missing-frontmatter` / `vault-frontmatter-no-title` (warn) — page has no
  closing `---` block, or one without a `title:`.
- `vault-orphan-page` (info) — no inbound `[[link]]`. `Home.md`, `raw/`,
  `.obsidian/`, and the auto-generated `Portfolio/` tree are excluded by the script.
- `log-malformed-entry` / `log-unknown-type` (warn) — a `log.md` heading that
  breaks the `## [YYYY-MM-DD] <type> | <title>` contract or uses a type outside the
  known set.

These findings are authoritative — a link the script calls broken *is* broken. Your
only judgment in this lane is flagging when an orphan or a forward-looking link is
intentional, which you note rather than silently drop.

### Judgment lane — your reading (not decidable by a script)

#### Possible contradictions (heuristic)

This is fuzzy and should be flagged as candidates, not verdicts. Look for:

- Pages sharing a tag or topic that make opposing factual claims about the same thing
  (version numbers, compatibility statements, "does X work with Y").
- Pages where one says "do X" and another says "do not do X".
- Pages whose `updated:` timestamps are very close but whose content disagrees.

Report each candidate as a pair of pages plus the specific sentences that appear to
conflict. Let the user judge.

#### Possible stale claims (heuristic)

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

Include counts in each heading so the user can scan the severity at a glance. The
Orphans / Broken wikilinks / Missing frontmatter sections are populated directly
from the validator findings (`vault-orphan-page`, `vault-broken-wikilink`,
`vault-missing-frontmatter` / `vault-frontmatter-no-title`); Contradictions and
Stale are your own. If `validate-log.sh` reported `log-*` findings, add a
`## log.md drift (N)` section for them.

## Log append

After producing the report, append a single entry to `<vault>/log.md`:

```
## [YYYY-MM-DD] lint | <N orphans, M broken, K missing frontmatter, L contradictions, P stale>
```

The log entry is a one-liner. The report itself is printed to the chat, not saved to
`log.md`. The `## [YYYY-MM-DD] <type> | …` shape and the `lint` type are enforced by
`validate-log.sh`, so this entry will pass the next lint's log check.

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

The mechanical lane no longer needs delegation: orphans, broken wikilinks, and
frontmatter are a single deterministic script run (`validate.sh`), faster and more
consistent than any subagent grep. Don't re-dispatch that work to `vault-scanner`.

Where `vault-scanner` (model: haiku) still earns its keep is the **judgment lane's
bulk reads**: when chasing possible contradictions or stale claims you may need to
read many pages that share a tag/topic. Delegate *those reads* — "return the
`updated:` date and any version/compatibility claims from these N pages" — and do
the comparison yourself. Bulk I/O to haiku; the verdict stays here.

## Common pitfalls

- **Running in fix mode by default.** Always report first.
- **Treating heuristics as verdicts.** Contradiction and staleness checks are
  candidates the user validates. The validator findings, by contrast, are decided.
- **Re-deriving the mechanical lane by hand.** Don't hand-grep for orphans or broken
  links — run `validate.sh` and trust it. It already excludes `raw/`/`.obsidian/`/
  `Portfolio/`, skips fenced code, and resolves aliases and path-style links, which
  hand-greps habitually get wrong.
- **Auto-deleting orphans.** Never. An orphan might be a page the user is about to
  link from a work-in-progress note.
- **Silently rewriting frontmatter.** Never. The user may have non-standard fields
  intentionally.
