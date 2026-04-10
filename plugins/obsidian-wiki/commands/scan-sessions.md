---
description: Scan recent AI coding sessions for vault-worthy moments
---

`<vault>` is the vault path resolved by `$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh`.


Use the `vault-session-scan` skill to discover sessions worth importing into the
Obsidian vault at `<vault>`. Reads from Claude Code, Codex, Cursor, Gemini,
and OpenCode session storage.

**Arguments**: `$ARGUMENTS` — `[tool] [days]`, both optional.

- `tool` ∈ `claude-code`, `codex`, `cursor`, `gemini`, `opencode`, or `all` (default).
- `days` is the lookback window (default: `7`).

If `$ARGUMENTS` is empty, scan all 5 tools over the last 7 days. This is a
**read-only** command — it surfaces a ranked list of candidates with suggested
filenames and categories. Pick a candidate and run `/obsidian-wiki:import-session` to
extract one.

**Examples**:
- `/obsidian-wiki:scan-sessions` — all 5 tools, last 7 days
- `/obsidian-wiki:scan-sessions claude-code` — Claude Code only, last 7 days
- `/obsidian-wiki:scan-sessions all 30` — all tools, last 30 days
- `/obsidian-wiki:scan-sessions codex 3` — Codex, last 3 days
