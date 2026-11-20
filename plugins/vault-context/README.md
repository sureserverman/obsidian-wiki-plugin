# vault-context

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](../../LICENSE)
[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-plugin-blueviolet)](https://docs.claude.com/en/docs/claude-code/plugins)

> Surface your Obsidian vault's knowledge inside the project repos where you actually work.

The companion plugin to [`obsidian-wiki`](../obsidian-wiki/README.md). Where `obsidian-wiki` runs from inside the vault to ingest, query, lint, and curate, `vault-context` runs from inside your **project repos** and brings the vault's accumulated knowledge into Claude Code's context — without you having to remember the vault has notes about whatever you're working on.

```text
cd ~/dev/some-project
/vault-context:link               # scan project, match vault, write .claude/vault-context.md
```

The first run generates `<project>/.claude/vault-context.md` listing every vault page relevant to the project (matched against project signals: manifests, README, dirs, recent commits) and adds a delimited `@.claude/vault-context.md` import block to project `CLAUDE.md`. From then on, every Claude Code session in that project loads the briefing eagerly. A SessionStart hook prompts to run `/vault-context:link` the first time you enter a fresh project.

`vault-context` is **read-only with respect to the vault**. Only `obsidian-wiki` writes there.

## How it works

```
[once, in vault]    /obsidian-wiki:index    →  <vault>/index.md
                                               (every page + tags + topics + 1-line summary)

[per project]       /vault-context:link     →  reads <vault>/index.md
                                            →  extracts project signals (manifests, dirs, README, git log)
                                            →  scores each indexed page (tag/topic/title overlap + recency)
                                            →  writes <project>/.claude/vault-context.md
                                            →  adds delimited @-import block to <project>/CLAUDE.md

[every future session in that project]  Claude Code auto-loads .claude/vault-context.md via the @-import.
                                         The briefing is in context before you even type.
```

## Install

`vault-context` lives in the same marketplace as `obsidian-wiki`:

```text
/plugin marketplace add sureserverman/obsidian-wiki-plugin
/plugin install obsidian-wiki@obsidian-wiki      # producer (vault side)
/plugin install vault-context@obsidian-wiki      # consumer (project side)
```

Restart Claude Code (or `/exit` and reopen) for the slash commands to register.

**Prerequisite**: a vault must be configured. See `obsidian-wiki`'s README for the bootstrap step that writes `~/.config/obsidian-wiki/config.json` and creates `<vault>/CLAUDE.md`, `log.md`, `raw/`. Then run `/obsidian-wiki:index` from the vault once to generate `<vault>/index.md` — `vault-context` reads that.

## Commands

| Command | What it does |
|---|---|
| `/vault-context:link` | First-time scan: write `.claude/vault-context.md` and add `@`-import to project `CLAUDE.md`. Errors if the sidecar already exists; pass `--force` to overwrite. |
| `/vault-context:refresh` | Re-scan the project and rewrite the sidecar. Use after vault changes + `/obsidian-wiki:index`. |
| `/vault-context:status` | Read-only report: vault path, index date, sidecar age, match count, import status. |
| `/vault-context:unlink` | Remove the sidecar and the delimited block from `CLAUDE.md`. Confirms first. |
| `/vault-context:sync-rules` | Write, update and remove the generated stack copies (`vault-stack-*.md`) in `${CLAUDE_CONFIG_DIR:-~/.claude}/vault-stacks` from the vault's stack pages, and remove copies an older release left in the Claude rules folder. `--check` writes nothing. Changes only files carrying the vault-context marker. |

## SessionStart hooks

Two `SessionStart` hooks ship with the plugin, both on `startup|resume|clear|compact|fork`.
`scripts/stack-context.py` adds the stack pages that apply to the project (see
[Stack rules](#stack-rules)). `scripts/session-start.sh` nudges; it checks five gates and exits silently unless **all** of them pass:

1. A vault is configured (env var, config file, or fallback)
2. `<vault>/index.md` exists
3. cwd is inside a git repo
4. cwd is **not** itself under the vault path (no circular linking)
5. `<cwd>/.claude/vault-context.md` does **not** already exist

When all five pass, the hook prints a one-line nudge:

```
[vault-context] No vault context for this project yet. Run `/vault-context:link` to scan your vault and surface relevant pages.
```

When the sidecar exists instead, the hook prints at most one other line, in this order:
a refresh nudge when the sidecar is older than `<vault>/index.md` (off with
`VAULT_CONTEXT_NO_STALENESS_NUDGE=1`, which silences that nudge only), else, when `<vault>/Portfolio/stacks/` exists and
`sync-stack-rules.py --check` reports drift (a copy `missing`, `stale`, `orphan`, or a
`legacy` copy left in the Claude rules folder), "Stack rules are out of date with the
vault. Run /vault-context:sync-rules."

Neither hook **ever modifies a file**. The user opts in by running the slash command.

## Vault discovery

Both plugins resolve the vault path the same way (mirrored `scripts/resolve-vault.sh`):

1. `OBSIDIAN_VAULT_PATH` env var (per-shell override)
2. `~/.config/obsidian-wiki/config.json` `default_vault` field
3. Hard fallback `~/dev/knowledge`

## Matching

`scripts/extract-project-signals.sh` collects deduplicated, normalized tokens from:

- Project name (dir basename + manifest `name` field)
- Manifest deps (top 30 from `package.json`, `requirements.txt`, `Cargo.toml`, `go.mod`, `pyproject.toml`)
- Top-level dir names at depth 1 (excluding `node_modules`, `.git`, `target`, `dist`, `build`, `.venv`, etc.)
- README H1/H2 headings
- Last 50 git commit subjects

`scripts/match-index.py` scores each indexed page:

- **Tag overlap** (signal token in page's `tags` field) — weight **3**
- **Topic overlap** (signal token in page's `topics` field) — weight **2**
- **Title-token overlap** (signal token in page title or alias tokens) — weight **1**
- **Rarity** — each matched token's weight is multiplied by `ln(N/df)` (N indexed pages, df pages holding the token), so process words found on many pages count for little
- **Recency boost** — page `updated:` within last 90 days → **+0.5**, only for a page that already matched

Top 30 pages with score > 0, at most **5** `Plans/` pages and **8** per other category, grouped by category. When at least 5 pages match, the project's own `Projects/` page (by title or file name) and its `Portfolio Integrations` page are always included. If fewer than 5 pages match, the matcher emits `NO_MATCHES` and the sidecar says so explicitly — so the SessionStart hook stops prompting.

Matching is token overlap — no embeddings, no stemming. Swap in `match-index.py` later if you want something fancier; the rest of the plugin doesn't change.

## Stack rules

A stack page in the vault (`Portfolio/stacks/<slug>.md`) holds the owner's file-keyed
facts for one stack, with `paths:` globs saying which files it is about.
`/vault-context:sync-rules` copies each page to `vault-stack-<slug>.md` in
`${CLAUDE_CONFIG_DIR:-~/.claude}/vault-stacks` (override: `--stacks-dir` or
`$VAULT_CONTEXT_STACKS_DIR`): frontmatter holding only `paths`, a marker line, then the
page body. At session start, resume, `/clear` and compaction, `scripts/stack-context.py`
takes the project root (the git top level of the session's folder, else the folder),
and adds every copy whose `paths` match a file the project holds to the session's
context, whole, up to 9,500 characters in all (Claude Code caps one hook at 10,000); a
copy that does not fit is named in one line with its path, to read. A project with no
matching file gets nothing; the page arrives at the next session start or `/clear`
after the first matching file is tracked. The hook reads only local files, never the
vault, and prints nothing on any error.

Generated copies are real files, so they keep working when the vault is not mounted;
they go stale when a page is edited, until the next sync. vault-context 0.6 wrote the
copies into `${CLAUDE_CONFIG_DIR:-~/.claude}/rules` instead, where Claude Code loads
them only when the model touches a matching file; the sync removes a marked copy left
there, since Claude Code would load it a second time. The nudge hook says so in one line; `/vault-context:status` reports `stack-*` findings. Each
project's sidecar names the stacks that apply to it under `## Stack rules`. The flow
is specified in `docs/workflows/WF-STACK-RULES.md`.

The same pages reach Cursor and Codex with `--host cursor|codex|all`:

| Host | What it gets | Why |
|---|---|---|
| Claude Code | `vault-stack-<slug>.md` in the stacks folder, added at session start by the hook | the hook decides per project which copies apply |
| Cursor | `<project>/.cursor/rules/vault-stack-<slug>.mdc` (`globs` = the page's paths, `alwaysApply: false`), only where the stack applies | Cursor attaches a rule when a matching file is in play, but reads no global rules folder, so each project gets its own; a project whose git would commit the rule is refused |
| Codex | copies in `${CODEX_HOME:-~/.codex}/vault-stacks/` and one pointer block in the home AGENTS file Codex reads (`AGENTS.override.md` when non-empty, else `AGENTS.md`) | Codex has no glob scoping and stops reading instructions at 32 KiB; eight pages inlined would pass that, so it gets one line per page naming the copy to read before touching a matching file |

Nothing is written under `~/.agents/` or into any project's own `AGENTS.md`.

## Safety guarantees

- **Vault is never written.** Only `obsidian-wiki` mutates the vault.
- **Project `CLAUDE.md` is touched only inside delimited markers.** The plugin owns `<!-- vault-context:start --> ... <!-- vault-context:end -->`. Surrounding content is left byte-identical.
- **Read-only by default.** `link`, `refresh`, `unlink` and `sync-rules` are the only commands that ever write. `status` is read-only.
- **Generated stack copies only.** `sync-rules` writes and removes only `vault-stack-*.md` files that carry its marker, in `${CLAUDE_CONFIG_DIR:-~/.claude}/vault-stacks` (or `$VAULT_CONTEXT_STACKS_DIR` when set), and removes marked ones left in `${CLAUDE_CONFIG_DIR:-~/.claude}/rules`. A same-named file without the marker, in either folder, stops the run untouched, and a missing or empty vault removes nothing. The Cursor and Codex hosts follow the same rule for `.cursor/rules/vault-stack-*.mdc` and `vault-stacks/*.md`, and change the Codex AGENTS file only between its `vault-context:stacks` markers.
- **Hooks never modify files.** The nudge hook only prints a prompt, and only in a directory `link` would actually accept; the stack hook only prints the applying stack copies.
- **Area directories are refused.** A grouping folder that merely holds project repos never gets a sidecar (exit 4), and the refusal happens before anything is created — no `.claude/` directory, no partial file. A directory counts as a project when no other registered project lives beneath it *and* it is either a git repo or a `path:` in the registry (see vault-portfolio's configuration).
- **No external services.** Everything runs locally; nothing leaves your machine.

## Determinism boundary

Mechanical, decidable checks live in `scripts/validate-link.sh` and decide
identically every run; the commands run them and consume the JSON rather than
re-deriving the rules. The validator owns a project's **link state**: the circular-link
guard, the area-directory guard, sidecar well-formedness, sidecar↔CLAUDE.md import
drift, and index freshness.

The area-directory rule lives once in `scripts/lib/eligibility.sh` and is shared by
three callers that must not disagree: the sidecar writer (`write-context.sh` refuses),
the detect path (`validate-link.sh` reports `link-area-directory` for a sidecar that
predates the guard), and the SessionStart hook (which nudges only where linking can
succeed — nudging elsewhere would repeat every session, since a refusal creates
nothing to silence it).
`/vault-context:status` reports its findings; the `link` skill runs it as a post-write
check. Judgment — which pages matter, status wording, when to refresh/unlink — stays
with the LLM. See `scripts/README.md` for the full split.

## Out of scope (v0.1)

- Multi-vault matching in one project session.
- Semantic / embedding-based matching.
- Auto-refresh on file changes.
- Writing project lessons back into the vault. (Use `/obsidian-wiki:import-session` from the vault side instead.)
- An MCP server exposing vault tools.

## License

[MIT](../../LICENSE).
