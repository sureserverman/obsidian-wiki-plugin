---
name: wiki-import-session
description: >
  Use when the user picks a specific AI coding session (Claude Code, Cursor, Codex, Gemini,
  OpenCode) to extract into the vault, mentions "/wiki-import-session", or asks to
  "import that session", "save this debugging arc to the wiki", "extract this conversation
  into raw/", or "turn yesterday's session into a note". Trigger after the user reviews a
  candidate from `wiki-scan-sessions` and chooses one.
---

> **Vault path:** `<vault>` is `default_vault` in `~/.config/obsidian-wiki/config.json` —
> **Read** that file; do not shell out. If it is missing, fall back to `~/dev/knowledge`.
> **Plugin root:** every `scripts/…` path below is relative to this plugin's install
> directory, `~/.cursor/plugins/local/obsidian-wiki/`.

# Vault Session Import

Take a single AI coding session — identified by path, UUID, or candidate ID from a prior
`wiki-scan-sessions` run — and turn it into a markdown source file under
`<vault>/raw/sessions/`. Optionally chain to `wiki-ingest` to file the resulting
source into the wiki proper.

This skill **writes one new file** in `raw/sessions/`. It does not edit existing wiki
pages — that's `wiki-ingest`'s job. The two-skill split lets the user review the
extracted markdown before it lands in the wiki.

## Step 1 — Resolve the session

Accept any of these inputs:

- Full path to a session file (`~/.claude/projects/.../<uuid>.jsonl`,
  `~/.codex/sessions/.../rollout-*.jsonl`, etc.)
- A bare UUID — search the 5 tool directories for a match.
- A candidate ID from a prior scan (e.g., `claude-code-2026-04-05-2b7b05df`) — translate
  back to the source path.

If the input is ambiguous, ask the user to confirm before continuing.

Identify the **tool** (claude-code, codex, cursor, gemini, opencode) from the path. The
tool determines the parser and the filename prefix. See
`../wiki-scan-sessions/references/storage-paths.md` for path-to-tool mapping.

## Step 2 — Idempotency check

Compute the canonical raw filename:

```
raw/sessions/<tool>-<YYYY-MM-DD>-<short-id>.md
```

Where:
- `<YYYY-MM-DD>` is the session start date (from filename or first event timestamp).
- `<short-id>` is the first 8 chars of the session UUID, or, for OpenCode, its
  `ses_` id with the prefix stripped (`ses_04661ff6…` → `04661ff6`).

**Cursor** adds one twist: session UUIDs are not globally unique across Cursor
project contexts. The idempotency key for Cursor is `(project_dir, session_uuid)`.
If the source path's project dir differs from the imported file's
`source-project:` / `source-session:` frontmatter, this is a DIFFERENT session
with a colliding UUID — use a disambiguated filename:

```
raw/sessions/cursor-<YYYY-MM-DD>-<short-id>-<project-slug>.md
```

where `<project-slug>` is a 6–10 char hint derived from the encoded cwd
(e.g. `emptywin`, `pihole`, `healthalert`). Only add the suffix when a
collision is detected.

**Codex** needs the same twist for a different reason: its session IDs are UUIDv7,
so the first 8 chars are a creation timestamp and sessions started within the same
few minutes share a short-id (one measured week: 32 rollouts, 29 unique short-ids,
one prefix covering three sessions 19 seconds apart). Compare the **full**
`session_id` from the source's `session_meta` event against the imported file's
`source-session:` frontmatter. If they differ, this is a different session with a
colliding short-id — disambiguate identically:

```
raw/sessions/codex-<YYYY-MM-DD>-<short-id>-<project-slug>.md
```

deriving the slug from `payload.cwd`; if that also matches, widen the short-id to
the UUID's first two groups (13 chars, e.g. `019ff7bf-981b`) rather than adding a
counter.

Then check **both** conditions:

1. Does some file in `<vault>/raw/sessions/` already carry this session's
   `source-uuid` (and, for Cursor, the same `source-project`)?
2. Does any wiki page's frontmatter `sources:` array contain that path?

Check (1) by **identity, not by filename**. The filename embeds a date, and the
date computed here (first event) is not the date the index computed (file mtime,
whenever no event timestamp is reachable — always for Cursor). A filename-only
check therefore misses a prior import whose date differs and writes a duplicate:
64 of the 606 rows on the 2026-08-14 worklist were in exactly that state.

If either is true, the default behavior is to **stop and tell the user** which
page already references this session — do not silently overwrite. Two reasons to
bypass with `--force`:

- **Refresh**: the source transcript has grown since the original import (common
  for Cursor and for Claude Code sessions resumed with `--continue`). The scan
  skill's "Refresh" bucket flags these; re-importing replaces the extraction
  with one that spans the full current arc.
- **User repair**: the prior extraction had errors and the user wants a redo.

On `--force`, set `refreshed: true` in the output frontmatter and mention the
prior turn count in the header (`"refreshed YYYY-MM-DD — original captured
~N of what is now M turns"`). See the Step 4 template.

## Step 3 — Stream-parse the session

Sessions can be huge (Claude Code: 10–100MB JSONL). **Never read the whole file into
context.** Stream line-by-line and extract only:

- The first user message (provides the topic / intent)
- All `assistant` text blocks (the explanations, not the tool calls)
- Tool results that contain errors (`is_error: true` or stderr)
- Any `summary` events (Claude Code's auto-summaries)
- The last user message (often contains the resolution or "thanks that worked")

Skip:
- Verbose tool inputs (file paths, command flags, full file contents)
- Successful tool results (build output, file lists) unless they're short
- System reminders, environment dumps, frontmatter blocks

**Per-tool parsing:** see `references/tool-parsers.md` for claude-code, codex,
cursor (agent-transcripts JSONL, with txt / SQLite fallbacks), gemini, and
opencode parsing rules. Load it when you have confirmed the tool in Step 1.

If a session is so dominated by code generation that there's no extractable narrative,
tell the user: this session has nothing vault-worthy. Don't fabricate content.

## Step 4 — Write the raw source file

The output goes to `<vault>/raw/sessions/<tool>-<YYYY-MM-DD>-<short-id>.md` with
this structure:

```markdown
---
title: <one-line topic, derived from the first user message>
source-tool: <claude-code|codex|cursor|gemini|opencode>
source-session: <full path to the original session file>
source-uuid: <session UUID if available>
source-project: <encoded-cwd path segment; required for cursor (for UUID-collision detection), optional for others>
extracted-on: <YYYY-MM-DD>
session-date: <YYYY-MM-DD>
session-turns: <count>
refreshed: <true|omit>   # set to true on --force re-imports
tags: [session, <tool>]
---

# <topic>

> Extracted from <tool> session on <date>. Original: `<path>`.

## Context

<1–2 paragraphs derived from the first user message + early assistant context. What was
the user trying to do?>

## Key moments

<3–8 bullet points capturing the substantive turns. Each bullet is one finding,
correction, gotcha, or insight. Quote the assistant verbatim when the wording is
load-bearing; paraphrase otherwise. Always note who said what.>

- **<short label>**: <quote or paraphrase>
- ...

## Errors and recoveries

<List of error → fix pairs from the session, if any. This is the highest-value content
for debugging-arc sessions. Include the error message verbatim; paraphrase the fix.>

- **<error summary>** → <fix>
- ...

## Resolution

<1 paragraph: did the session end with a working solution? If so, what was it? If
not, where did it stall?>

## Verbatim excerpts

<Optional. Include 1–3 short verbatim quotes from the session that capture the most
load-bearing reasoning or correction. Use blockquotes. Do not include >50 lines total.>
```

Be ruthless about length. The raw file should be **2–5 KB**, not 50 KB. Long
verbatim dumps belong in the original JSONL, not in the wiki source.

## Step 5 — Append to log

Append to `<vault>/log.md`:

```
## [YYYY-MM-DD] session-import | <topic>
- Tool: <tool>
- Source: raw/sessions/<filename>
- Original: <full path to session file>
- Turns: <N>
```

`session-import` is a log type alongside `ingest`, `query`, `lint`, `schema`,
`gaps`, `merge`, `session-capture`, `index`. The `vault-CLAUDE.md` schema
documents this list.

### Cross-reference back to a capture entry

If the import was triggered from `review-captures` (a Claude Code-side skill, not
in this port: the user picked a
capture queued by the Claude Code plugin's session capture), append one extra bullet that points
back to the originating `session-capture` entry:

```
- Captured-as: [<capture-date>] session-capture <short-id>
```

Where `<capture-date>` is the `[YYYY-MM-DD]` from the original capture
entry's heading and `<short-id>` is the same 8-char prefix of the session
UUID. This is the **only** authoritative marker that the Claude Code-side `review-captures`
uses to tell pending captures from imported ones, so do not skip it for
capture-driven imports. Manual imports (where the user passed a path
directly to `/wiki-import-session` and there's no capture entry
in the log) omit this line.

## Step 6 — Offer to chain into ingest

After writing the raw file and logging, ask the user:

> Wrote `raw/sessions/<filename>`. Want to ingest it into the wiki now? (Y/n)

If yes, hand off to `wiki-ingest` with the new file as input. The ingest skill handles
category selection, cross-refs, and the wiki page creation independently.

If no, leave the file in `raw/sessions/`. The user can run `/wiki-ingest
raw/sessions/<filename>` later.

## What never to do

- **Do not slurp the entire session file into context.** A 100MB JSONL will blow your
  context window. Stream-parse line-by-line, extract only the relevant events.
- **Do not write into a wiki category dir** (`Architecture/`, `Gotchas/`, etc.). That's
  `wiki-ingest`'s job, not this skill's. Session imports always land in
  `raw/sessions/` first.
- **Do not fabricate content.** If a session has no extractable narrative (pure code
  generation, no diagnostic turns), tell the user. Don't invent insights to justify the
  import.
- **Do not overwrite an existing raw file** without `--force`. The idempotency check is
  there to protect prior imports — possibly with manual edits the user made. When
  `--force` is used for a refresh, set `refreshed: true` in frontmatter and append
  a `Refresh: true` line to the log entry so the audit trail distinguishes refreshes
  from first imports.
- **Do not edit the original session file.** It's source-of-truth provenance. Treat
  `~/.claude/projects/`, `~/.codex/`, etc. as read-only.
- **Do not include secrets verbatim.** If you spot API keys, tokens, passwords, or
  paths to credential files in the session, redact them in the extracted markdown.
  Note that you redacted (`<redacted: api key>`) so the user knows.

## Delegation (optional, for cost/speed)

Step 3 (stream-parse extraction) and Step 4 (writing the structured raw file)
are exactly the content-transformation shape a smaller worker is built for.
Delegate both to the `wiki-vault-writer` Cursor subagent. Give it:

- the resolved session path, the tool name, the canonical `raw/sessions/`
  filename, and the session UUID/short-id,
- the "what to extract / what to skip" rules from Step 3,
- the output template from Step 4 (frontmatter + sections),
- the 2–5 KB target size and the redaction rule for secrets.

Keep Step 1 (resolution), Step 2 (idempotency check against both disk and
existing `sources:` references), Step 5 (log append with the precise
`session-import` format, including the `Captured-as:` line when applicable),
and Step 6 (the chain-into-ingest offer) in this session — those touch other
vault files and need the caller's context about user intent.

## Common pitfalls

- **Wrong tool detection.** A session moved or symlinked from another location may
  fool the path-based detection. Read the first event to confirm — Claude Code events
  have a recognizable `type: "user"` shape; Codex events look different.
- **Missing UUID.** OpenCode session ids are `ses_`-prefixed, not UUIDs; strip the
  prefix and take 8 chars. (Older builds stored no id at all — if you meet one, use
  the first 8 chars of the
  project hash (the JSON filename) as the short-id.
- **Date drift.** The session's filesystem mtime is not the session start date. Use
  the first event's timestamp (or, for Codex, parse the ISO timestamp from the
  filename). Always normalize to `YYYY-MM-DD` in the output filename.
- **Forgetting the log entry.** The append-only log is the audit trail. Skipping it
  means a session can be re-imported later because there's no record.
- **Treating the raw file as the wiki page.** The raw file is a source — it goes into
  `raw/sessions/`, not into a category dir. Ingest is a separate step.
