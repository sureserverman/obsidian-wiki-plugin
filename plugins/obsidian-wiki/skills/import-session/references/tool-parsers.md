# Per-tool parsing notes

Parsing rules for each supported AI coding tool, referenced by Step 3
("Stream-parse the session") of `import-session`. Load this file when
actually parsing a session — the skill body only names which tool applies.

- **Claude Code JSONL**: each line is `{type, message: {role, content}}`. `content` is
  an array of blocks; pull `text` blocks from assistant, skip `tool_use`/`tool_result`
  unless errored.
- **Codex JSONL**: every event is `{timestamp, ordinal, type, payload}`; the real
  content lives under `payload`, whose shape depends on `type` (`session_meta`,
  `event_msg`, `response_item`, …), so field names differ from Claude Code's.
  Inspect the first 5 lines to confirm the schema for the installed `cli_version`.
  Line 1 is always `session_meta` and carries `payload.session_id` (full UUIDv7 —
  the idempotency key), `payload.cwd`, `payload.timestamp` (true session start,
  earlier than the enclosing event's own timestamp), and `payload.originator` /
  `payload.thread_source`. **Check those last two before extracting anything**: only
  `codex-tui` + `user` is a real interactive session. `codex_exec` is non-interactive
  automation and `subagent` is a spawned thread — both produce transcripts that look
  session-shaped but carry no diagnostic arc, and both are usually the majority of a
  window. If the caller handed you one anyway, say so rather than importing it.
- **Cursor agent-transcripts JSONL** (primary): path shape
  `~/.cursor/projects/<encoded-cwd>/agent-transcripts/<uuid>/<uuid>.jsonl`. Each
  line is `{"role": "user"|"assistant", "message": {"content": [...]}}`. Content
  blocks are `text` and `tool_use` only — there are **no `tool_result` events**
  (Cursor doesn't write tool output back into the transcript), so the scan's
  "errored tool_result" signal doesn't apply; infer errors from assistant text
  that follows a tool_use. There are **no in-event timestamps** and no session
  metadata header — derive the session start date from the transcript file's
  mtime, and the session UUID from the filename. Pull `text` blocks from both
  roles; skip `tool_use` inputs (paths, globs, file contents) unless the
  invocation itself is the point of a "what did you do" moment.
- **Cursor agent-tools .txt** (secondary, rarely the right input): plain text
  tool outputs only — not conversations. Only use when the user explicitly
  pointed at one; the resulting raw file will be more like a captured log than
  an extracted session.
- **Cursor SQLite (state.vscdb)** (fallback): only if `agent-transcripts/` is
  missing or the user specifically asked. Use
  `sqlite3 ... "SELECT value FROM ItemTable WHERE key LIKE '%composerData%';"`
  and decode the JSON blobs. Schema is undocumented; inspect first.
- **Gemini JSON**: one document per session at
  `~/.gemini/tmp/<project>/chats/session-<datetime>-<short-id>.json` — **not** under
  `~/.gemini/history/`, which holds only `.project_root` markers. Slurpable (tens of
  KB to ~1 MB). Shape: `{sessionId, projectHash, startTime, lastUpdated, messages:
  [{id, timestamp, type, content: [{text}]}]}` where `type` is `user` or `gemini`.
  Every message carries its own timestamp, so dates need no mtime inference.
- **OpenCode JSON**: read the file (small), find the messages/turns array, iterate.
