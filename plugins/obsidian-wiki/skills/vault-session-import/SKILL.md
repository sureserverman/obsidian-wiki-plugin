---
name: vault-session-import
description: >
  Use when the user picks a specific AI coding session (Claude Code, Cursor, Codex, Gemini,
  OpenCode) to extract into the vault, mentions "/vault-import-session", or asks to
  "import that session", "save this debugging arc to the wiki", "extract this conversation
  into raw/", or "turn yesterday's session into a note". Trigger after the user reviews a
  candidate from `vault-session-scan` and chooses one.
---

# Vault Session Import

Take a single AI coding session — identified by path, UUID, or candidate ID from a prior
`vault-session-scan` run — and turn it into a markdown source file under
`~/dev/knowledge/raw/sessions/`. Optionally chain to `vault-ingest` to file the resulting
source into the wiki proper.

This skill **writes one new file** in `raw/sessions/`. It does not edit existing wiki
pages — that's `vault-ingest`'s job. The two-skill split lets the user review the
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
`../vault-session-scan/references/storage-paths.md` for path-to-tool mapping.

## Step 2 — Idempotency check

Compute the canonical raw filename:

```
raw/sessions/<tool>-<YYYY-MM-DD>-<short-id>.md
```

Where:
- `<YYYY-MM-DD>` is the session start date (from filename or first event timestamp).
- `<short-id>` is the first 8 chars of the session UUID, or, for OpenCode (no UUID),
  the first 8 chars of the project hash.

Then check **both** conditions:

1. Does `~/dev/knowledge/raw/sessions/<filename>` already exist?
2. Does any wiki page's frontmatter `sources:` array contain that path?

If either is true, **stop and tell the user** which page already references this session.
Do not silently overwrite. The user can pass `--force` to bypass (rare).

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

Per-tool parsing notes:

- **Claude Code JSONL**: each line is `{type, message: {role, content}}`. `content` is
  an array of blocks; pull `text` blocks from assistant, skip `tool_use`/`tool_result`
  unless errored.
- **Codex JSONL**: similar event structure but the field names differ (`role` may be
  nested under `payload` or `message` depending on version). Inspect first 5 lines to
  determine the schema.
- **Cursor agent-tools .txt**: plain text already; no parsing needed. Just read the
  file. These are tool outputs only — there's no "assistant explanation" to extract,
  so the resulting raw file will be more like a captured log.
- **Cursor SQLite (state.vscdb)**: only if the user specifically asked. Use
  `sqlite3 ... "SELECT value FROM ItemTable WHERE key LIKE '%composerData%';"` and
  decode the JSON blobs. Schema is undocumented; inspect first.
- **Gemini**: best-effort. Read whatever files exist in the project's history dir.
- **OpenCode JSON**: read the file (small), find the messages/turns array, iterate.

If a session is so dominated by code generation that there's no extractable narrative,
tell the user: this session has nothing vault-worthy. Don't fabricate content.

## Step 4 — Write the raw source file

The output goes to `~/dev/knowledge/raw/sessions/<tool>-<YYYY-MM-DD>-<short-id>.md` with
this structure:

```markdown
---
title: <one-line topic, derived from the first user message>
source-tool: <claude-code|codex|cursor|gemini|opencode>
source-session: <full path to the original session file>
source-uuid: <session UUID if available>
extracted-on: <YYYY-MM-DD>
session-date: <YYYY-MM-DD>
session-turns: <count>
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

Append to `~/dev/knowledge/log.md`:

```
## [YYYY-MM-DD] session-import | <topic>
- Tool: <tool>
- Source: raw/sessions/<filename>
- Original: <full path to session file>
- Turns: <N>
```

`session-import` is a new log type, alongside `ingest`, `query`, `lint`, `schema`,
`gaps`, `merge`. The `vault-CLAUDE.md` schema documents this list.

## Step 6 — Offer to chain into vault-ingest

After writing the raw file and logging, ask the user:

> Wrote `raw/sessions/<filename>`. Want to ingest it into the wiki now? (Y/n)

If yes, hand off to `vault-ingest` with the new file as input. The ingest skill handles
category selection, cross-refs, and the wiki page creation independently.

If no, leave the file in `raw/sessions/`. The user can run `/vault-ingest
raw/sessions/<filename>` later.

## What never to do

- **Do not slurp the entire session file into context.** A 100MB JSONL will blow your
  context window. Stream-parse line-by-line, extract only the relevant events.
- **Do not write into a wiki category dir** (`Architecture/`, `Gotchas/`, etc.). That's
  `vault-ingest`'s job, not this skill's. Session imports always land in
  `raw/sessions/` first.
- **Do not fabricate content.** If a session has no extractable narrative (pure code
  generation, no diagnostic turns), tell the user. Don't invent insights to justify the
  import.
- **Do not overwrite an existing raw file** without `--force`. The idempotency check is
  there to protect prior imports — possibly with manual edits the user made.
- **Do not edit the original session file.** It's source-of-truth provenance. Treat
  `~/.claude/projects/`, `~/.codex/`, etc. as read-only.
- **Do not include secrets verbatim.** If you spot API keys, tokens, passwords, or
  paths to credential files in the session, redact them in the extracted markdown.
  Note that you redacted (`<redacted: api key>`) so the user knows.

## Common pitfalls

- **Wrong tool detection.** A session moved or symlinked from another location may
  fool the path-based detection. Read the first event to confirm — Claude Code events
  have a recognizable `type: "user"` shape; Codex events look different.
- **Missing UUID.** OpenCode sessions don't have UUIDs. Use the first 8 chars of the
  project hash (the JSON filename) as the short-id.
- **Date drift.** The session's filesystem mtime is not the session start date. Use
  the first event's timestamp (or, for Codex, parse the ISO timestamp from the
  filename). Always normalize to `YYYY-MM-DD` in the output filename.
- **Forgetting the log entry.** The append-only log is the audit trail. Skipping it
  means a session can be re-imported later because there's no record.
- **Treating the raw file as the wiki page.** The raw file is a source — it goes into
  `raw/sessions/`, not into a category dir. Ingest is a separate step.
