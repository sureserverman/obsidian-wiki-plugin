# obsidian-wiki

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-plugin-blueviolet)](https://docs.claude.com/en/docs/claude-code/plugins)
[![Inspired by Karpathy](https://img.shields.io/badge/inspired%20by-Karpathy's%20LLM--wiki-orange)](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

> Turn Claude into a librarian for your Obsidian vault — without restructuring it.

A Claude Code plugin that brings the [LLM-wiki workflow](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) to an Obsidian vault you already use. Ingest sources, query with `[[wikilink]]` citations, lint for orphans and stale claims, and auto-capture vault-worthy moments from your AI coding sessions as they end.

```text
/obsidian-wiki:ingest raw/article.md            # file a source into the wiki
/obsidian-wiki:ask what do I know about X       # cited answer from your notes
/obsidian-wiki:lint                             # find orphans, broken links, stale pages
/obsidian-wiki:review-captures                  # triage what the SessionEnd hook flagged
```

15 slash commands. 12 skills. Read-only by default — only `ingest`, `import-session`, `merge`, schema edits, `lint fix`, and `index` ever write to the vault. A SessionEnd hook auto-queues vault-worthy sessions for review without ever extracting them on its own.

## Install

**1. Install the plugins** in any Claude Code session:

```text
/plugin marketplace add sureserverman/obsidian-wiki-plugin
/plugin install obsidian-wiki@obsidian-wiki
/plugin install vault-context@obsidian-wiki    # optional companion (see below)
```

Restart Claude Code (or `/exit` and reopen) for the slash commands to register.

**2. Bootstrap your vault** (one-time; touches nothing that already exists):

```bash
mkdir -p ~/dev/knowledge/raw/assets
BASE=https://raw.githubusercontent.com/sureserverman/obsidian-wiki-plugin/main/plugins/obsidian-wiki/assets
curl -fLsS "$BASE/vault-CLAUDE.md" -o ~/dev/knowledge/CLAUDE.md
curl -fLsS "$BASE/log-template.md" -o ~/dev/knowledge/log.md

mkdir -p ~/.config/obsidian-wiki
cat > ~/.config/obsidian-wiki/config.json <<'EOF'
{ "default_vault": "~/dev/knowledge", "vaults": { "knowledge": "~/dev/knowledge" } }
EOF
```

This adds `CLAUDE.md`, `log.md`, `raw/`, and a tiny config file at `~/.config/obsidian-wiki/config.json` that both plugins read to find your vault. Your existing notes, `Home.md`, and `.obsidian/` are untouched. Edit `CLAUDE.md` once to match your vault's conventions; from then on it's edited only via the `vault-schema-maintain` skill.

**3. Try it:**

```text
/obsidian-wiki:stats              # see what your vault looks like today
/obsidian-wiki:lint               # find orphans, broken links, stale claims
/obsidian-wiki:index              # build the machine-readable digest at <vault>/index.md
```

## Companion plugin: vault-context

`obsidian-wiki` runs from inside the vault. Its companion `vault-context` runs from inside your **project repos** and surfaces vault knowledge there — without you having to remember the vault has notes on what you're working on.

```text
cd ~/dev/some-project
/vault-context:link               # scan project, match vault index, write .claude/vault-context.md
```

The first run generates `<project>/.claude/vault-context.md` listing every vault page relevant to the project (matched from `<vault>/index.md` against project signals: manifests, README, dirs, recent commits) and adds a delimited `@.claude/vault-context.md` import block to project `CLAUDE.md`. From then on, every Claude Code session in that project loads the briefing eagerly. A SessionStart hook prompts to run `/vault-context:link` the first time you enter a fresh project.

`vault-context` is **read-only with respect to the vault** — only `obsidian-wiki` writes there. See `plugins/vault-context/README.md` for the full command list.

## Commands

### Core

| Command | What it does |
|---|---|
| `/obsidian-wiki:ingest <path>` | Process a source from `raw/` into a wiki page (interactive if no arg) |
| `/obsidian-wiki:ask <question>` | Query the wiki with `[[wikilink]]` citations on every claim |
| `/obsidian-wiki:lint` | Health check report (read-only); add `fix` for interactive fix mode |
| `/obsidian-wiki:log [N]` | Show recent entries from `log.md` grouped by type |

<details>
<summary><b>Maintenance commands</b> — stats, gaps, related, rebuild-home, tag, merge</summary>

| Command | What it does |
|---|---|
| `/obsidian-wiki:stats` | Vault dashboard: counts, hubs, orphans, recent activity, stale candidates |
| `/obsidian-wiki:related <page>` | Suggest missing cross-references for one page |
| `/obsidian-wiki:gaps [N]` | Find entities mentioned by ≥N pages with no dedicated page yet |
| `/obsidian-wiki:rebuild-home` | Refresh `Home.md` tables to match files on disk |
| `/obsidian-wiki:tag [tags...]` | Filter pages by tag (AND semantics), or show tag cloud |
| `/obsidian-wiki:tag --moc <tag>` | Propose a Markdown table for a tag MOC |
| `/obsidian-wiki:merge <loser> <survivor>` | Merge two pages, rewrite all inbound wikilinks |

</details>

<details>
<summary><b>Session import</b> — mine AI coding sessions across Claude Code, Codex, Cursor, Gemini, OpenCode</summary>

| Command | What it does |
|---|---|
| `/obsidian-wiki:scan-sessions [tool] [days]` | Scan recent agent sessions for vault-worthy moments |
| `/obsidian-wiki:import-session <id-or-path>` | Extract one session into `raw/sessions/`, then offer to ingest |
| `/obsidian-wiki:review-captures` | Review pending captures the SessionEnd hook auto-queued |

Stream-parses head/tail/error windows; never slurps GB into context. Idempotent — re-runs are no-ops unless you pass `--force`.

A SessionEnd hook (`scripts/capture-session.sh`) fires when any Claude Code session ends, scores it via lightweight heuristics, and (if vault-worthy) appends a `session-capture` log entry to `<vault>/log.md`. Nothing is extracted at capture time — `/obsidian-wiki:review-captures` is what later turns the queue into actual `raw/sessions/` files. Opt out per shell with `OBSIDIAN_WIKI_NO_CAPTURE=1`, per project with a `.obsidian-wiki-no-capture` marker file, or tune sensitivity with `OBSIDIAN_WIKI_CAPTURE_THRESHOLD=N`.

</details>

## How it works

<details>
<summary>Three layers, append-only log, idempotent writes</summary>

**Three layers:**

| Layer | Purpose | Edited by |
|---|---|---|
| **Raw** | Immutable source files: articles, PDFs, extracted sessions | Never |
| **Wiki** | Hand-curated markdown in your category dirs | Plugin adds and updates pages; never restructures |
| **Schema** | `CLAUDE.md` — categories, frontmatter, naming, ingest rules | `vault-schema-maintain` skill, surgically, with confirmation |

**Append-only log.** Every write appends to `log.md` with type ∈ `{ingest, query, lint, schema, merge, gaps, session-import, session-capture, index}`. Past entries are never edited.

**Idempotent.** A source has been ingested if its path appears in some page's `sources:` frontmatter — re-runs update rather than duplicate. Session imports are no-ops if either the canonical `raw/sessions/<tool>-<date>-<id>.md` exists or any wiki page already cites the session.

**Default vault layout** (adapt `CLAUDE.md` to your own):

```text
~/dev/knowledge/
├── Architecture/  Gotchas/  Patterns/  Platforms/  Projects/  Technologies/
├── Home.md              # Map-of-Content index (hand-curated)
├── CLAUDE.md            # vault schema (added by bootstrap)
├── log.md               # append-only activity log (added by bootstrap)
├── raw/                 # source inbox + raw/sessions/ + raw/assets/
└── .obsidian/           # untouched
```

</details>

## Staying up to date

`obsidian-wiki` ships a `SessionStart` hook that runs `git fetch` against the marketplace clone at most once every 6 hours and prints a one-line nudge when commits land upstream. To apply:

```text
/obsidian-wiki:update
```

Shows the `git log` changelog, asks for confirmation, runs `claude plugin marketplace update` + `claude plugin update` for every installed plugin from this marketplace, then reminds you to restart. If you want a persistent statusline badge instead of the session nudge, paste `plugins/obsidian-wiki/scripts/statusline-snippet.sh` into your own statusline script — plugins can't contribute to the statusline directly, so it's opt-in.

Manual fallback: `/plugin marketplace update obsidian-wiki && /plugin update obsidian-wiki@obsidian-wiki`.

## License & credits

[MIT](LICENSE). Built directly from [Andrej Karpathy's LLM-wiki workflow gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). Session-import is an extension for multi-tool AI coding workflows; everything else is a faithful adaptation of the three-layer model.
