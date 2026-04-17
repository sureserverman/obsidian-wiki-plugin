# Per-tool parsing notes

Parsing rules for each supported AI coding tool, referenced by Step 3
("Stream-parse the session") of `vault-session-import`. Load this file when
actually parsing a session — the skill body only names which tool applies.

- **Claude Code JSONL**: each line is `{type, message: {role, content}}`. `content` is
  an array of blocks; pull `text` blocks from assistant, skip `tool_use`/`tool_result`
  unless errored.
- **Codex JSONL**: similar event structure but the field names differ (`role` may be
  nested under `payload` or `message` depending on version). Inspect first 5 lines to
  determine the schema.
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
- **Gemini**: best-effort. Read whatever files exist in the project's history dir.
- **OpenCode JSON**: read the file (small), find the messages/turns array, iterate.
