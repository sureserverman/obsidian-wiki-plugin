# obsidian-wiki

A Claude Code plugin that implements [Karpathy's LLM-wiki workflow](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) over an existing Obsidian vault.

The plugin provides twelve skills and fifteen slash commands. Claude Code namespaces
all plugin commands as `/<plugin-name>:<command>`, so every command in this plugin is
invoked as `/obsidian-wiki:<command>` — no risk of collision with built-in commands
like `/login`. The plugin is built to **adapt to a vault that already has its own
structure** rather than imposing Karpathy's exact `raw/ + wiki/ + index.md` layout.

**Skills**: `ingest`, `ask`, `lint`, `vault-schema-maintain`,
`related`, `gaps`, `rebuild-home`, `merge`,
`scan-sessions`, `import-session`, `review-captures`, `index`.

**Commands**: `/obsidian-wiki:ingest`, `/obsidian-wiki:ask`, `/obsidian-wiki:lint`, `/obsidian-wiki:log`,
`/obsidian-wiki:stats`, `/obsidian-wiki:related`, `/obsidian-wiki:gaps`, `/obsidian-wiki:rebuild-home`, `/obsidian-wiki:tag`,
`/obsidian-wiki:merge`, `/obsidian-wiki:scan-sessions`, `/obsidian-wiki:import-session`,
`/obsidian-wiki:review-captures`, `/obsidian-wiki:index`, `/obsidian-wiki:update`.

## What it does

**Core workflow** (Karpathy's three operations + schema):

- **Ingest** a source from `raw/` into the wiki: writes a summary page in the right
  category, adds backlinks to related pages, optionally updates the index, appends to
  a log.
- **Query** the wiki with citations: reads the index first, drills into relevant pages,
  cites every claim with `[[wikilinks]]`, optionally files valuable answers back as
  new pages.
- **Lint** the vault for orphans, broken wikilinks, missing frontmatter, possible
  contradictions, and possibly stale claims. Report-only by default.
- **Schema maintenance**: evolve the vault's `CLAUDE.md` rules over time as
  conventions are corrected.

- **Vault index**: regenerate `<vault>/index.md`, a machine-readable digest of every
  page (title, path, tags, topics, one-line summary, updated date) for downstream tools
  like the `vault-context` companion plugin.

**Maintenance helpers** (the work Karpathy says "humans abandon"):

- **Stats dashboard**: page counts per category, hub pages, orphan count, recent
  activity, possibly stale pages.
- **Find related**: for a given page, suggest cross-references it should have but
  doesn't.
- **Find gaps**: entities mentioned across multiple pages that lack a dedicated page
  yet.
- **Rebuild Home.md**: regenerate the index tables when manual page additions or
  deletions in Obsidian have caused drift.
- **Tag filter**: Dataview-style frontmatter filter — list pages by tag, optionally
  generate a tag-based MOC.
- **Merge**: consolidate two pages into one and rewrite every inbound wikilink.
- **Session scan**: discover vault-worthy moments across recent AI coding sessions
  (Claude Code, Codex, Cursor, Gemini, OpenCode), score them, and surface ranked
  candidates without writing anything.
- **Session import**: extract one chosen session into `raw/sessions/` as a markdown
  source, then optionally chain into ingest to file it into the wiki.

## Vault layout assumed

The plugin is configured for a vault at `~/dev/knowledge` with this layout:

```
~/dev/knowledge/
├── Architecture/        # system designs
├── Gotchas/             # surprises and footguns
├── Patterns/            # reusable approaches
├── Platforms/           # per-platform notes
├── Projects/            # per-project notes
├── Technologies/        # per-tool notes
├── Home.md              # Map-of-Content index
├── CLAUDE.md            # vault schema (added by bootstrap)
├── log.md               # append-only activity log (added by bootstrap)
├── raw/                 # source inbox (added by bootstrap)
│   ├── assets/          # images and binaries
│   └── sessions/        # extracted AI coding sessions (created on first import)
└── .obsidian/           # Obsidian config (untouched)
```

The six category directories and `Home.md` already exist. The bootstrap step adds
`CLAUDE.md`, `log.md`, and `raw/`. **No existing files are touched.**

## Install

The plugin lives inside a single-plugin marketplace at `~/dev/obsidian-wiki-plugin/`.
Layout:

```
~/dev/obsidian-wiki-plugin/
├── .claude-plugin/marketplace.json    # marketplace manifest
└── plugins/obsidian-wiki/             # the plugin itself
    ├── .claude-plugin/plugin.json
    ├── skills/
    ├── commands/
    └── assets/
```

To install in Claude Code, run these slash commands in any session:

```
/plugin marketplace add ~/dev/obsidian-wiki-plugin
/plugin install obsidian-wiki@obsidian-wiki
```

The first command registers the local marketplace; the second installs the plugin
from it. Claude Code will copy the plugin into its own cache and enable it. Restart
Claude Code (or open a new session) for the slash commands to appear.

To update after editing the source, run `/plugin marketplace update obsidian-wiki`
followed by `/plugin install obsidian-wiki@obsidian-wiki` again.

## Bootstrap the vault

The plugin does not modify the vault automatically. Run these one-time commands:

```bash
mkdir -p ~/dev/knowledge/raw/assets
cp ~/dev/obsidian-wiki-plugin/assets/vault-CLAUDE.md ~/dev/knowledge/CLAUDE.md
cp ~/dev/obsidian-wiki-plugin/assets/log-template.md ~/dev/knowledge/log.md
```

Verify:

```bash
test -f ~/dev/knowledge/CLAUDE.md && \
test -f ~/dev/knowledge/log.md && \
test -d ~/dev/knowledge/raw/assets && \
echo "vault bootstrapped"
```

If your vault is a git repo, `git status --short` should show only the three new
paths as untracked. Existing wiki files are not touched.

Edit `~/dev/knowledge/CLAUDE.md` afterward to tweak category rules, frontmatter
fields, or any conventions specific to your vault. From then on, that file is edited
only via the `vault-schema-maintain` skill.

## Usage

Open Claude Code with `~/dev/knowledge` as the working directory.

### Core commands

| Command | What happens |
|---|---|
| `/obsidian-wiki:ingest raw/article.md` | process a source into a wiki page |
| `/obsidian-wiki:ingest` | list files in `raw/` and ask which to ingest |
| `/obsidian-wiki:ask what do I know about Tor DNS leaks` | query the wiki with citations |
| `/obsidian-wiki:lint` | run all five health checks, print a report (read-only) |
| `/obsidian-wiki:lint fix` | enter fix mode, confirms each edit individually |
| `/obsidian-wiki:log` | show the last 10 entries from `log.md` grouped by type |
| `/obsidian-wiki:log 25` | show the last 25 entries |

### Maintenance commands

| Command | What happens |
|---|---|
| `/obsidian-wiki:stats` | dashboard: page counts, hubs, orphans, recent activity, stale candidates |
| `/obsidian-wiki:stats verbose` | also include per-category orphan and hub breakdowns |
| `/obsidian-wiki:related Gotchas/DNS Leaks.md` | suggest missing cross-refs for one page (read-only) |
| `/obsidian-wiki:gaps` | find entities mentioned by ≥3 pages with no dedicated page yet |
| `/obsidian-wiki:gaps 2` | lower the threshold to ≥2 pages |
| `/obsidian-wiki:rebuild-home` | refresh `Home.md` tables to match files on disk (with diff confirmation) |
| `/obsidian-wiki:tag` | show tag cloud of every tag in the vault with page counts |
| `/obsidian-wiki:tag tor dns` | list pages tagged with both `tor` AND `dns` |
| `/obsidian-wiki:tag --moc tor` | generate a Markdown table for a `tor` MOC (does not write it) |
| `/obsidian-wiki:merge old-page.md canonical-page.md` | merge two pages, rewrite all inbound wikilinks, delete the loser |

### Session import commands

| Command | What happens |
|---|---|
| `/obsidian-wiki:scan-sessions` | scan all 5 tools for vault-worthy sessions in last 7 days (read-only report) |
| `/obsidian-wiki:scan-sessions claude-code 30` | scan one tool, last 30 days |
| `/obsidian-wiki:import-session <id-or-path>` | extract one session into `raw/sessions/`, then offer to ingest |
| `/obsidian-wiki:import-session <id> --no-ingest` | write the raw file but skip the ingest prompt |
| `/obsidian-wiki:review-captures` | review pending captures the SessionEnd hook queued; pick which to import |
| `/obsidian-wiki:review-captures all` | show every pending capture, no display cap |

### Index command

| Command | What happens |
|---|---|
| `/obsidian-wiki:index` | regenerate `<vault>/index.md` — machine-readable digest of every wiki page, used by the `vault-context` companion plugin |

### Self-update

| Command | What happens |
|---|---|
| `/obsidian-wiki:update` | check the `obsidian-wiki` marketplace for upstream commits, show the git-log changelog, confirm, and apply the update via `claude plugin marketplace update` + `claude plugin update` |

A `SessionStart` hook (`scripts/check-update.sh`) runs a `git fetch` against
the marketplace clone in the background at most once every 6 hours, writes the
result to `/tmp/claude/obsidian-wiki-update-check.json`, and prints a one-line
nudge at session start when an update is available. The hook never modifies
any file — it only reports. Running `/obsidian-wiki:update` is what actually
applies the update, and it will prompt before changing anything.

### Auto-capture from SessionEnd

A second hook (`scripts/capture-session.sh`) fires on `SessionEnd` from any
project. It scores the just-ended session via lightweight heuristics — long
sessions, error clusters, substantive endings, user-satisfaction markers — and
if the score crosses the threshold (default 2, override with
`OBSIDIAN_WIKI_CAPTURE_THRESHOLD=N`) appends a `session-capture` entry to
`<vault>/log.md`. The hook spawns a detached background process so the user's
session-end is never blocked, and never extracts the session content — that's
the job of `/obsidian-wiki:review-captures` later.

The hook only writes to the vault's `log.md` (under `flock`). It never writes
to `raw/`, the wiki, or anything in the project the session ran in. Captures
are idempotent (a session-id is only ever captured once), and the hook
silently skips if the cwd is the vault itself, the reason is `clear`, the
project has a `.obsidian-wiki-no-capture` marker file, or
`OBSIDIAN_WIKI_NO_CAPTURE=1` is set in the shell environment.

For a persistent **statusline badge** instead of the one-off session nudge,
paste the snippet from `scripts/statusline-snippet.sh` into your own Claude
Code statusline script (see that file's header comment for instructions).
Claude Code plugins cannot contribute to the statusline directly, so the
badge is opt-in. If you skip it, the session nudge still works.

The skills also auto-trigger from natural-language phrases — see each `SKILL.md` for
the trigger list.

## Design principles

- **The vault is not a database.** Every operation is a careful edit, not a
  rebuild-from-scratch.
- **The wiki layer is hand-curated.** Existing pages, `Home.md`, and `.obsidian/` are
  never restructured. The plugin adds, never reorganizes.
- **Append-only audit trail.** Every operation that changes the wiki appends to
  `log.md`. Past entries are never edited.
- **Contradictions are surfaced, not resolved.** When a source disagrees with the
  vault, the plugin flags it and asks the user.
- **Heuristics report candidates, not verdicts.** Lint's contradiction and staleness
  checks are fuzzy by design.
- **Trigger-only skill descriptions.** Skill descriptions contain only the user
  phrases that should trigger them — never workflow steps. (See
  `skill-description-leak-audit` for the reasoning.)

## File map

```
obsidian-wiki-plugin/                # marketplace root
├── .claude-plugin/
│   └── marketplace.json             # marketplace manifest (single plugin)
└── plugins/
    └── obsidian-wiki/                # the plugin
├── .claude-plugin/
│   └── plugin.json
├── hooks/
│   └── hooks.json               # SessionStart + SessionEnd hook registration
├── README.md
├── skills/
│   ├── ingest/SKILL.md
│   ├── ask/SKILL.md
│   ├── lint/SKILL.md
│   ├── vault-schema-maintain/SKILL.md
│   ├── related/SKILL.md
│   ├── gaps/SKILL.md
│   ├── rebuild-home/SKILL.md
│   ├── merge/SKILL.md
│   ├── index/SKILL.md
│   ├── scan-sessions/
│   │   ├── SKILL.md
│   │   └── references/storage-paths.md
│   ├── import-session/SKILL.md
│   └── review-captures/SKILL.md
├── commands/
│   ├── ingest.md
│   ├── ask.md
│   ├── lint.md
│   ├── log.md
│   ├── stats.md
│   ├── related.md
│   ├── gaps.md
│   ├── rebuild-home.md
│   ├── tag.md
│   ├── merge.md
│   ├── scan-sessions.md
│   ├── import-session.md
│   ├── review-captures.md
│   ├── index.md
│   └── update.md
├── scripts/
│   ├── resolve-vault.sh        # vault path resolver (mirrored in vault-context)
│   ├── check-update.sh         # SessionStart hook: background marketplace update check
│   ├── capture-session.sh      # SessionEnd hook: score + queue vault-worthy sessions
│   ├── score-session.py        # JSONL scorer used by capture-session.sh
│   └── statusline-snippet.sh   # opt-in snippet for statusline badge
└── assets/
    ├── vault-CLAUDE.md       # template dropped into the vault
    └── log-template.md       # initial log.md
```

## Out of scope (for v0.1)

- Obsidian Web Clipper integration (Karpathy mentions it, but the plugin assumes
  sources already exist in `raw/`).
- The `qmd` CLI / MCP server for fast vector + BM25 retrieval over the wiki.
- Dataview plugin queries over frontmatter.

These can be added in a later iteration if useful.
