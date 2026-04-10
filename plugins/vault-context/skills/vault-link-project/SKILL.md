---
name: vault-link-project
description: >
  Use when the user asks what their Obsidian vault knows about the current project
  repo, asks to link/refresh vault context for a project, mentions
  "/vault-context:link" or "/vault-context:refresh", or opens an unfamiliar project
  and wants a vault briefing. Trigger on "what does my vault say about this project",
  "link my notes here", "pull vault context for this repo", "any gotchas in my notes
  for this codebase", "brief me on this project from my vault", or when a SessionStart
  hook reports that no vault-context.md exists yet.
---

# Vault Link Project

Make the Obsidian vault's accumulated knowledge available inside a project repo by
matching the vault's index against signals from the current project, writing a
plugin-owned sidecar at `<project>/.claude/vault-context.md`, and ensuring project
`CLAUDE.md` references that sidecar so future Claude Code sessions load the briefing
automatically.

The vault is **read-only** from this skill's perspective. Only files inside the
project are written. The vault's `index.md` (read here) is generated separately by
`obsidian-wiki:index`.

## Preconditions

Resolve the vault path with `${CLAUDE_PLUGIN_ROOT}/scripts/resolve-vault.sh`. The
resolver tries `OBSIDIAN_VAULT_PATH`, then `~/.config/obsidian-wiki/config.json`'s
`default_vault`, then `<vault>`. If the resolver exits non-zero, no vault is
configured — tell the user to run the bootstrap step from `obsidian-wiki`'s README.

`<vault>/index.md` must exist. If it doesn't, the producer plugin's
`/obsidian-wiki:index` has never been run. Tell the user:

> The vault's index file is missing. Run `/obsidian-wiki:index` from your vault first,
> then re-run `/vault-context:link`.

**Refuse to run if cwd is inside the vault itself.** That would be a circular link
(a vault page asking for vault context about itself). Compare `realpath cwd` against
`realpath vault`; if cwd is at or under vault, exit with a clear message.

## Project signal extraction

Invoke `${CLAUDE_PLUGIN_ROOT}/scripts/extract-project-signals.sh` against the cwd.
The script reads:

- Project name (directory basename + `name` field in `package.json`/`pyproject.toml`/`Cargo.toml`/`go.mod`)
- Manifest dependency names (top 30 from `package.json`, `requirements.txt`, `Cargo.toml`, `go.mod`)
- Top-level directory names at depth 1 (excluding noise: `node_modules`, `.git`, `target`, `dist`, `build`, `.venv`, `__pycache__`)
- README H1/H2 headings if `README.md` exists
- Recent commit subjects (`git log -50 --format=%s`) if cwd is a git repo

The output is a deduplicated, normalized list of tokens — one per line, lowercase,
alphanumeric+hyphen, stopwords removed.

## Match against the vault index

Pipe the signals into `${CLAUDE_PLUGIN_ROOT}/scripts/match-index.py`:

```bash
extract-project-signals.sh | match-index.py "<vault>/index.md"
```

The matcher scores each index entry by:

- **Tag overlap** (signal token in page's `tags` field) — weight 3 per match
- **Topic overlap** (signal token in page's `topics` field) — weight 2 per match
- **Title-token overlap** (signal token appears in page title tokens) — weight 1 per match
- **Recency boost** — page `updated:` within last 90 days → flat +0.5

Output: JSON to stdout. Top 30 pages by score (only those scoring > 0), grouped by
the category dir parsed from `path:`. If fewer than 5 pages score > 0, the matcher
emits a single line `NO_MATCHES` instead — surface that to the user as
"no relevant vault pages found for this project" but still write the sidecar so the
SessionStart hook stops prompting.

## Write the sidecar

Invoke `${CLAUDE_PLUGIN_ROOT}/scripts/write-context.sh <project name> <vault path>`
with the matcher's JSON on stdin. The script:

1. Loads `${CLAUDE_PLUGIN_ROOT}/assets/vault-context-template.md`.
2. Substitutes `<PROJECT_NAME>`, `<DATE>`, `<VAULT_PATH>`, `<INDEX_DATE>`, `<MATCH_COUNT>`.
3. Renders matches as one bullet per page, grouped by category, in this format:
   ```
   - [[Page Title]] — `<absolute path>` — <one-line summary from index>
   ```
   Absolute paths so Claude can `Read` them directly without cwd guesswork.
4. Writes the result to `<cwd>/.claude/vault-context.md`, creating `.claude/` if missing.

## Update project CLAUDE.md

Make the sidecar discoverable from project `CLAUDE.md` so every future Claude Code
session loads it eagerly via the `@<file>` import directive.

The plugin owns a delimited block:

```markdown
<!-- vault-context:start -->
@.claude/vault-context.md
<!-- vault-context:end -->
```

Algorithm:

- If `<cwd>/CLAUDE.md` does not exist: create it with just the delimited block above
  (plus a single header line so the file isn't bare).
- If it exists and **already contains** `<!-- vault-context:start -->`: leave the
  surrounding content alone, replace only what's between the start and end markers.
- If it exists and does **not** contain the markers: append the block at the end of
  the file separated by a blank line.

Never edit content outside the markers. The delimited block is the only part the
plugin claims ownership of.

## Report

Tell the user:

- Vault path that was used.
- Date of `<vault>/index.md` (so they know how stale the source is).
- Number of pages matched (or "no matches").
- Path of the new sidecar.
- Whether project `CLAUDE.md` was created or updated (and that the change is confined
  to the delimited block).

If the index date is more than 30 days old, suggest running `/obsidian-wiki:index`
from the vault to refresh it before the next link.

## Common pitfalls

- **Running inside the vault itself** — refuse. Linking the vault to itself is
  meaningless and will index recursively in a way the user didn't ask for.
- **Running with no `<vault>/index.md`** — point at `/obsidian-wiki:index`, don't try
  to grep the vault directly. The matcher needs the structured digest.
- **Treating `vault-context.md` as user-editable** — it isn't. The header says it's
  auto-generated; future runs overwrite it without asking. Hand-edits belong in the
  vault, not in the sidecar.
- **Editing project `CLAUDE.md` outside the delimited block** — never. The user owns
  the rest of that file. The plugin only mutates content between
  `<!-- vault-context:start -->` and `<!-- vault-context:end -->`.
- **Duplicating the delimited block** — when re-running, replace in place; don't
  append a second copy.
- **Silently overwriting an existing sidecar without telling the user** — always
  report whether you replaced or created. Use `/vault-context:refresh` (not `:link`)
  for explicit re-runs.
- **Pulling page bodies into the sidecar** — only summaries from the index. Page
  bodies are read on-demand by Claude using the absolute paths in the sidecar.
