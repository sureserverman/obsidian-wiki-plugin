---
description: Extract one AI coding session into raw/sessions/ as a markdown source for the vault
---

Use the `vault-session-import` skill to extract one session into
`~/dev/knowledge/raw/sessions/` as a markdown file. After writing, the skill offers to
chain into `vault-ingest` so the source can be filed into the wiki proper.

Arguments: $ARGUMENTS

Expected format: a session identifier — any of:

- A full path: `~/.claude/projects/-home-user-dev-room/2b7b05df-...jsonl`
- A bare UUID: `2b7b05df-3a8c-4f1d-9b8e-1234567890ab`
- A candidate ID from a recent `/vault-scan-sessions` run:
  `claude-code-2026-04-05-2b7b05df`

If `$ARGUMENTS` is empty, ask the user which session — and suggest running
`/vault-scan-sessions` first if they don't already have a candidate in mind.

The skill is **idempotent**: it refuses to overwrite an existing
`raw/sessions/<file>.md` and refuses to re-import a session already cited by some
wiki page. Pass `--force` only when you intentionally want to replace an existing
extract.

Special flags:
- `--force` — overwrite an existing extract (rare; use when re-extracting after a
  parser bug fix).
- `--no-ingest` — write the raw file but skip the chained `vault-ingest` prompt.
