---
name: scan-sessions
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
import into the wiki via `import-session`.

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
  then **drop non-interactive rollouts** — read line 1 (`session_meta`) of each and
  keep only `payload.originator == "codex-tui"` with `payload.thread_source ==
  "user"`. `codex_exec` runs and `subagent` threads are automation, not sessions,
  and are typically the majority of the window (see the reference)
- **Cursor**: `find ~/.cursor/projects -path '*/agent-transcripts/*/*.jsonl' -mtime -<days>`
  (full transcripts — these are the real conversations, not the `agent-tools/*.txt`
  files which are tool outputs only; for the SQLite fallback see the reference)
- **Gemini**: `find ~/.gemini/tmp -path '*/chats/session-*.json' -mtime -<days>`
  (**not** `~/.gemini/history/`, which holds only `.project_root` markers)
- **OpenCode**: `find ~/.local/share/opencode/storage/project -name '*.json' -mtime -<days>`

If a tool's directory doesn't exist, skip it silently — the user may not use all 5.

**A zero result is a claim — check which kind it is.** "No sessions in the window"
and "I looked in the wrong place" are indistinguishable in the output, and both
Gemini and OpenCode shipped wrong paths in this skill until 0.7.2. Before reporting
zero for any tool, confirm the store is reachable and non-empty *without* the date
filter — drop `-mtime` (or the `time_updated` clause) and count. Then report which
one you found: "no sessions in the last N days (M total on disk, newest
YYYY-MM-DD)" or "storage not found at <path> — the tool may be uninstalled, or this
skill's path may be stale." Never report a bare zero.

## Step 3 — Filter, but check for staleness

For each candidate session, derive the canonical raw filename:

```
raw/sessions/<tool>-<YYYY-MM-DD>-<short-id>.md
```

Where `<short-id>` is the first 8 chars of the session UUID (or, for OpenCode, the
first 8 chars of the project hash).

Then check both idempotency conditions:

1. Does `<vault>/raw/sessions/<filename>` exist?
2. Does any wiki page's frontmatter `sources:` contain that path?

If **neither** is true, the session is a fresh candidate — score it and include it.

If **either** is true, do not silently drop it. Some tools (Cursor in particular,
also Claude Code sessions resumed with `--continue`, and OpenCode project-scoped JSON)
append to the same session file across days, so the imported extraction may be stale.
Apply the **staleness check**:

```
source_mtime     = mtime of the current source session file
imported_mtime   = mtime of raw/sessions/<filename>.md
source_size      = line count (JSONL) or event count (JSON) of the source
imported_turns   = `session-turns:` field of the imported file's frontmatter

stale if:
    (source_mtime - imported_mtime) > 1 day
  AND (source_size >= imported_turns * 1.25  OR  source_size - imported_turns >= 50)
```

Tune both conditions: mtime alone can lie (transcript opened without edits), size
alone can lie (small appends). Together they catch real growth.

A stale candidate enters a separate **Refresh** bucket in the report — do not mix it
with fresh candidates. Score it the same way, but annotate it with the original
import date and the growth factor (e.g. `190 → 2969 turns, 15×`).

### Cursor-specific: UUID collisions across projects

Cursor reuses session UUIDs across different project contexts — e.g. the same
`93512520-…` UUID can exist under `~/.cursor/projects/empty-window/` **and**
`~/.cursor/projects/home-user-dev-foo/` with different content. Before assuming a
Cursor candidate is already imported, check the imported file's
`source-project:` frontmatter (or `source-session:` path) against the candidate's
project dir. If they differ, treat it as a **new session with a colliding UUID** and
suggest a disambiguated filename:

```
raw/sessions/cursor-<YYYY-MM-DD>-<short-id>-<project-slug>.md
```

Where `<project-slug>` is a short (6–10 char) hint derived from the encoded cwd —
e.g. `emptywin`, `pihole`, `healthalert`.

### Codex-specific: short-ID collisions within a day

Codex session IDs are **UUIDv7**, whose first 8 hex chars encode the creation
timestamp — so they are not random and sessions started within the same few minutes
share a `<short-id>`. In one measured 7-day window, 32 rollouts produced 29 unique
short-IDs: one prefix covered three sessions started 19 seconds apart. Writing them
under the plain name would silently overwrite.

Dedupe Codex candidates by the **full** `session_id` from the `session_meta` event,
not the short-id, and disambiguate the raw filename the same way as Cursor:

```
raw/sessions/codex-<YYYY-MM-DD>-<short-id>-<project-slug>.md
```

deriving `<project-slug>` from `payload.cwd`. If two colliding sessions also share a
cwd, widen the short-id to the UUID's first two groups (13 chars, e.g.
`019ff7bf-981b`) instead of adding a counter.

Cursor and Codex are the only tools needing this; Claude Code, Gemini and OpenCode
IDs are unique within a day.

Show counts: fresh candidates, refresh candidates, dropped-as-current, dropped as
non-interactive (Codex), and new-with-colliding-ID (Cursor, Codex) separately, so the
user can tell the scan was thorough.

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

> **Do not score with `scripts/score-session.py`.** That scorer belongs to the
> SessionEnd capture hook and parses the **Claude Code** event shape only
> (`message.content[].type == "text"`). Pointed at a Codex rollout or a Cursor
> transcript it does not error — it silently returns a flat, meaningless score for
> every session, because it finds no text, no roles, and no `is_error` events. It
> refuses such input as of 0.7.1, but the scoring above is the contract for this
> skill on every tool, including Claude Code: sample and judge, don't shell out.

### Trigger heuristics (label what made a session worth capturing)

Tag each candidate with any of four **canonical trigger heuristics** it exhibits
(these are the exact labels the coder-plugins `session-analyzer` / `skill-workshop`
use — spell them identically so the two toolchains stay in sync). These are a
**secondary label**, not a second scoring pass: the numeric 0–5 score above is
unchanged; the trigger tags ride into the report so an `import-session` pick
inherits the "why this mattered" context.

| Trigger | Signal in the session | Related Step-4 row |
|---|---|---|
| `user-correction` | the user corrected the agent's approach and the corrected approach then worked | (no numeric row — label only) |
| `error-resolved` | an error was resolved through visible trial-and-error (≥2 failed attempts) | "Multiple failed attempts before success" |
| `nonobvious-workflow` | a working procedure that needed discovery/lookup, not derivation | "Introduced a new tool / protocol" |
| `recurring-toolchain` | the same 5+ tool sequence the user keeps re-driving by hand | (no numeric row — label only) |

Where a trigger maps to a Step-4 row, that row already contributed its points —
do **not** add the trigger's points again. The tag records the reason; it never
double-counts the score.

## Step 5 — Build the candidate report

Group by tool, sort by score within each group. Separate **Fresh** candidates
(never imported) from **Refresh** candidates (already imported but the source
has grown past the staleness threshold — Step 3). Annotate each candidate with
any trigger heuristics it matched (e.g. `[user-correction, error-resolved]`) so
the reason it scored is visible at a glance and rides along into `import-session`.

```markdown
# Session scan — last 7 days

## Claude Code (4 fresh, 1 refresh, 3 current)

### Fresh — high value
1. **2026-04-05 — Tor bridge bootstrap debugging** (score 5, 87 turns)
   - `~/.claude/projects/-home-user-dev-room/2b7b05df-...jsonl`
   - Snippet: "obfs4 bridges fail on first connect but succeed on retry"
   - Suggested import name: `raw/sessions/claude-code-2026-04-05-2b7b05df.md`
   - Suggested category: `Gotchas/`

### Fresh — medium value
2. **2026-04-04 — Refactoring xray config** (score 2, 34 turns)
   - ...

### Refresh (imported file stale — source grew since last import)
3. **2026-04-02 — long-running skill dev session** (190 → 2100 turns, 11×)
   - Imported: `raw/sessions/claude-code-2026-04-02-aaaaaaaa.md` (extracted 2026-04-03)
   - Source mtime: 2026-04-12
   - Re-import with `/obsidian-wiki:import-session --force` to refresh

## Codex (2 fresh)
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

- **Do not write to `raw/`.** That's `import-session`'s job.
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
- the list of already-imported raw filenames with their mtimes and
  `session-turns:` values (for the staleness check in Step 3),
- the scoring signals table, and ask it to return one row per candidate session
  with `tool`, `date`, `path`, `short_id`, `project_slug` (Cursor only),
  `turn_count`, `score`, `dominant_signals`, `bucket` (`fresh` | `refresh` |
  `colliding-uuid`), and a ≤2-sentence snippet.

Keep the `references/storage-paths.md` read, the idempotency filter (including the
staleness and UUID-collision logic), and the candidate-report formatting in this
session — those benefit from the caller's context about user intent.

## Common pitfalls

- **Reading entire sessions.** Always sample. Use head/tail/error windows.
- **Missing tool dirs.** Some tools may not be installed; skip silently — but say
  so in the report rather than folding them into a zero count (see Step 2).
- **Cursor wrong-directory trap.** The full conversations live under
  `agent-transcripts/<uuid>/<uuid>.jsonl` — always scan there. The
  `agent-tools/*.txt` files are captured tool outputs (build logs, command
  output), **not** sessions, and their UUID is a tool-invocation UUID not a
  session UUID. The `state.vscdb` SQLite mirror is version-dependent and slow;
  only dive into it when `agent-transcripts/` is missing or the user is hunting
  a specific conversation they remember.
- **Cursor has no in-event timestamps.** Transcript events are only `{role,
  message}`. Derive the session start date from the file's or directory's mtime,
  not from the events.
- **Cursor has no tool_result events.** The "errored tool_result" scoring
  signal doesn't fire on Cursor — infer failures from assistant text following
  a `tool_use` block instead.
- **Cursor session UUIDs are not globally unique.** The same UUID prefix can
  appear under two different `~/.cursor/projects/<cwd>/agent-transcripts/`
  directories with different content. Do not dedupe Cursor candidates by
  UUID alone — include the project path. See Step 3.
- **Silently dropping "already imported" sessions.** Cursor and Claude Code
  append to the same session file across days. An imported file extracted on
  day 1 may be stale by day 7. Use the Step 3 staleness check (mtime + size
  growth), not just filename existence.
- **Importing Codex automation as if it were a session.** Most rollouts in a
  window are `codex_exec` (non-interactive) or `subagent` threads — in one measured
  week, 25 of 32. They read as sessions but are review-agent transcripts. Filter on
  the `session_meta` first line; see Step 2.
- **Deduping Codex by short-id.** UUIDv7 prefixes are timestamps, so sessions
  minutes apart collide. Use the full `session_id`. See Step 3.
- **Scoring non-Claude-Code sessions with the capture hook's scorer.** See the
  note in Step 4 — it parses one tool's shape and quietly flattens the rest.
- **Date encoding mismatches.** Each tool dates sessions differently. Always normalize
  to ISO `YYYY-MM-DD` in the report. Codex's true start is `payload.timestamp` in the
  `session_meta` event; a Claude Code session's is its first event's timestamp, not
  the file mtime (long-running sessions drift days past their start date).
- **Forgetting to dereference the working directory.** Claude Code and Cursor encode
  the cwd into the path. Use the encoding rules from `references/storage-paths.md`.
