---
description: Extract one AI coding session into raw/sessions/ as a vault source
---

`<vault>` is the vault path resolved by `$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh`.


Use the `vault-session-import` skill to extract one session into
`<vault>/raw/sessions/` as a markdown file. After writing, the skill offers to
chain into `vault-ingest` so the source can be filed into the wiki.

**Arguments**: `$ARGUMENTS` — a session identifier. Any of:

- A full path to a session file
- A bare UUID
- A candidate ID from a recent `/obsidian-wiki:scan-sessions` run (e.g.
  `claude-code-2026-04-05-2b7b05df`)

If `$ARGUMENTS` is empty, ask which session — and suggest running `/obsidian-wiki:scan-sessions`
first if the user doesn't already have a candidate in mind. The skill is **idempotent**:
it refuses to overwrite an existing `raw/sessions/<file>.md` and refuses to re-import a
session already cited by some wiki page.

## Special arguments

- `--force` — overwrite an existing extract (rare; use after a parser bug fix).
- `--no-ingest` — write the raw file but skip the chained `vault-ingest` prompt.

**Examples**:
- `/obsidian-wiki:import-session claude-code-2026-04-05-2b7b05df`
- `/obsidian-wiki:import-session ~/.codex/sessions/2026/04/05/rollout-...jsonl --no-ingest`
- `/obsidian-wiki:import-session 2b7b05df-3a8c-4f1d-9b8e-1234567890ab --force`
