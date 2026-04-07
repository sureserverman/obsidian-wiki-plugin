---
description: Scan recent AI coding sessions across Claude Code, Codex, Cursor, Gemini, OpenCode for vault-worthy moments
---

Use the `vault-session-scan` skill to discover sessions worth importing into the
Obsidian vault at `~/dev/knowledge`.

Arguments: $ARGUMENTS

Expected format: `[tool] [days]`. Both optional.

- `tool` ∈ `claude-code`, `codex`, `cursor`, `gemini`, `opencode`, or `all` (default).
- `days` is the lookback window (default `7`).

Examples:
- `/vault-scan-sessions` — all 5 tools, last 7 days
- `/vault-scan-sessions claude-code` — Claude Code only, last 7 days
- `/vault-scan-sessions all 30` — all tools, last 30 days
- `/vault-scan-sessions codex 3` — Codex, last 3 days

The skill is **read-only**. It never writes to `raw/`, the wiki, or `log.md`. It only
surfaces a ranked list of candidates with suggested filenames and categories. Pick a
candidate and run `/vault-import-session` to actually extract one.
