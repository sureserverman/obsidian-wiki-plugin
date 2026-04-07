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
| `/vault-context:unlink` | Remove the sidecar and the delimited block from `CLAUDE.md`. The only destructive command — confirms first. |

## SessionStart hook

A `SessionStart` hook ships with the plugin. It checks five gates and exits silently unless **all** of them pass:

1. A vault is configured (env var, config file, or fallback)
2. `<vault>/index.md` exists
3. cwd is inside a git repo
4. cwd is **not** itself under the vault path (no circular linking)
5. `<cwd>/.claude/vault-context.md` does **not** already exist

When all five pass, the hook prints a one-line nudge:

```
[vault-context] No vault context for this project yet. Run `/vault-context:link` to scan your vault and surface relevant pages.
```

The hook **never modifies a file**. The user opts in by running the slash command.

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
- **Title-token overlap** (signal token in page title tokens) — weight **1**
- **Recency boost** — page `updated:` within last 90 days → flat **+0.5**

Top 30 pages with score > 0, grouped by category. If fewer than 5 pages match, the matcher emits `NO_MATCHES` and the sidecar says so explicitly — so the SessionStart hook stops prompting.

Matching is intentionally simple (token overlap, no embeddings, no stemming). Swap in `match-index.py` later if you want something fancier; the rest of the plugin doesn't change.

## Safety guarantees

- **Vault is never written.** Only `obsidian-wiki` mutates the vault.
- **Project `CLAUDE.md` is touched only inside delimited markers.** The plugin owns `<!-- vault-context:start --> ... <!-- vault-context:end -->`. Surrounding content is left byte-identical.
- **Read-only by default.** `link`, `refresh`, and `unlink` are the only commands that ever write. `status` is read-only.
- **Hook never modifies files.** It only prints a prompt.
- **No external services.** Everything runs locally; nothing leaves your machine.

## Out of scope (v0.1)

- Multi-vault matching in one project session.
- Semantic / embedding-based matching.
- Auto-refresh on file changes.
- Writing project lessons back into the vault. (Use `/obsidian-wiki:import-session` from the vault side instead.)
- An MCP server exposing vault tools.

## License

[MIT](../../LICENSE).
