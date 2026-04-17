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
- **Cursor agent-tools .txt**: plain text already; no parsing needed. Just read the
  file. These are tool outputs only — there's no "assistant explanation" to extract,
  so the resulting raw file will be more like a captured log.
- **Cursor SQLite (state.vscdb)**: only if the user specifically asked. Use
  `sqlite3 ... "SELECT value FROM ItemTable WHERE key LIKE '%composerData%';"` and
  decode the JSON blobs. Schema is undocumented; inspect first.
- **Gemini**: best-effort. Read whatever files exist in the project's history dir.
- **OpenCode JSON**: read the file (small), find the messages/turns array, iterate.
