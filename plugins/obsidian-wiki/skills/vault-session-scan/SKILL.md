---
name: vault-session-scan
allowed-tools: Read, Glob, Grep, Bash
description: >
  Use when the user asks to find vault-worthy moments from recent AI coding sessions
  across Claude Code, Cursor, Codex, Gemini, or OpenCode, mentions "/obsidian-wiki:scan-sessions",
  or asks "what should I capture from my agent sessions". Trigger on "mine my sessions
  for the wiki", "find lessons from yesterday's debugging", "what did I learn this week",
  or "scan recent agent sessions for raw/".
---

> **Vault path:** `<vault>` refers to the path returned by `$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh`. Run it first to resolve the vault location.

# Vault Session Scan

Discover recent sessions across the user's AI coding tools (Claude Code, Codex, Cursor,
Gemini, OpenCode), score them for vault-worthiness, and present candidates the user can
import into the wiki via `vault-session-import`.

This skill is **read-only** — it never writes to `raw/`, the wiki, or `log.md`. It only
surfaces candidates.

## Step 1 — Read the storage reference

Read `references/storage-paths.md` (sibling file in this skill directory). It documents
where each tool stores sessions and the parsing notes. Trust it over your own assumptions
about paths — these tools change format between versions.

## Step 2 — Discover sessions

For each tool the user named (or all 5 if no tool was specified), enumerate the
candidate session files within the time window (default: last 7 days; configurable via
the `<days>` argument).

For each tool, the discovery method differs — see `references/storage-paths.md`. The
fastest enumerations:

- **Claude Code**: `find ~/.claude/projects -name '*.jsonl' -mtime -<days>`
- **Codex**: `find ~/.codex/sessions/<YYYY>/<MM> -name 'rollout-*.jsonl' -mtime -<days>`
- **Cursor**: `find ~/.cursor/projects -name '*.txt' -mtime -<days>` (agent-tools only;
  for chat history, see the SQLite section in the reference)
- **Gemini**: `find ~/.gemini/history -type f -mtime -<days>` plus
  `~/.gemini/antigravity/knowledge/` and `brain/` if they contain markdown
- **OpenCode**: `find ~/.local/share/opencode/storage/project -name '*.json' -mtime -<days>`

If a tool's directory doesn't exist, skip it silently — the user may not use all 5.

## Step 3 — Filter out already-imported sessions

For each candidate session, derive the canonical raw filename:

```
raw/sessions/<tool>-<YYYY-MM-DD>-<short-id>.md
```

Where `<short-id>` is the first 8 chars of the session UUID (or, for OpenCode, the
first 8 chars of the project hash).

Then check both idempotency conditions:

1. Does `<vault>/raw/sessions/<filename>` exist?
2. Does any wiki page's frontmatter `sources:` contain that path?

If either is true, drop the session from the candidate list. Show the kept count and
the filtered count separately so the user knows the scan was thorough.

## Step 4 — Score for vault-worthiness

The user does not want every session in the wiki — most sessions are routine code
edits or quick questions. Score each remaining session 0–5 based on these signals
(higher = more vault-worthy):

| Signal | Weight |
|---|---|
| Long session (>50 message turns) | +1 |
| Multiple failed attempts before success (debugging arc) | +2 |
| Introduced a new tool / protocol / library not yet in the vault | +2 |
| Ended with a working solution to a non-trivial problem | +1 |
| Mentions an entity already covered by a Gotcha or Pattern page | +1 |
| Routine refactor / typo fix / "what's the syntax for X" | −2 |
| Failed to converge — user gave up | −1 |
| Pure code generation, no diagnostic content | −1 |

Apply the score by sampling each session: read the first 30 events, the last 30
events, and the events around any tool failures (errors in tool_result events). You
do not need to read the entire session; the head/tail/error windows give enough signal.

Sessions with score ≥ 3 are "high-value", 1–2 are "medium", 0 or negative is "low".

## Step 5 — Build the candidate report

Group by tool, sort by score within each group:

```markdown
# Session scan — last 7 days

## Claude Code (4 candidates, 3 already imported, 1 skipped)

### High value
1. **2026-04-05 — Tor bridge bootstrap debugging** (score 5, 87 turns)
   - `~/.claude/projects/-home-user-dev-room/2b7b05df-...jsonl`
   - Snippet: "obfs4 bridges fail on first connect but succeed on retry"
   - Suggested import name: `raw/sessions/claude-code-2026-04-05-2b7b05df.md`
   - Suggested category: `Gotchas/`

### Medium value
2. **2026-04-04 — Refactoring xray config** (score 2, 34 turns)
   - ...

## Codex (2 candidates)
...
```

For each candidate include:
- Session date
- A one-line topic (derived from the first user message or summary event)
- Score with the dominant signals that produced it
- The full session path (so the user can open it)
- A short snippet (1–2 sentences) from the most-relevant section
- The suggested `raw/sessions/` filename
- The suggested wiki category

Keep the report scannable. Cap each tool group at 10 entries. If more exist, say
"+ N more, run with longer window" at the bottom of the group.

## Step 6 — Don't log

Scans don't get logged. Only imports do. If the user wants a record of what was
considered, they can re-run the scan — it's idempotent.

## What never to do

- **Do not write to `raw/`.** That's `vault-session-import`'s job.
- **Do not modify any wiki page.** Scanning is read-only.
- **Do not slurp full session files into context.** A 100MB JSONL will blow your
  context window. Stream-parse, sample head/tail/errors only.
- **Do not invent scores.** The score must be backed by signals you actually observed
  in the sample.
- **Do not skip the idempotency check.** A scan that re-suggests already-imported
  sessions is annoying noise.

## Delegation (optional, for cost/speed)

Steps 2 (discovery) and 4 (scoring by sampling JSONL head/tail/error windows) are
the read-heavy phases. If you are running on Opus, delegate them to the
`vault-scanner` subagent (model: haiku) via the Agent tool with
`subagent_type: vault-scanner`. Give it:

- the list of tool storage roots to walk,
- the `<days>` window,
- the list of already-imported raw filenames (for the filter in step 3),
- the scoring signals table, and ask it to return one row per candidate session
  with `tool`, `date`, `path`, `short_id`, `turn_count`, `score`, `dominant_signals`,
  and a ≤2-sentence snippet.

Keep the `references/storage-paths.md` read, the idempotency filter, and the
candidate-report formatting in this session — those benefit from the caller's
context about user intent.

## Common pitfalls

- **Reading entire sessions.** Always sample. Use head/tail/error windows.
- **Missing tool dirs.** Some tools may not be installed; skip silently.
- **Cursor SQLite trap.** The `state.vscdb` files are version-dependent and slow to
  query. Default to the agent-tools `.txt` files; only dive into SQLite if the user
  asks for chat history specifically.
- **Date encoding mismatches.** Each tool dates sessions differently. Always normalize
  to ISO `YYYY-MM-DD` in the report.
- **Forgetting to dereference the working directory.** Claude Code and Cursor encode
  the cwd into the path. Use the encoding rules from `references/storage-paths.md`.
