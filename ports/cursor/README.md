# ports/cursor — obsidian-wiki for Cursor (manual skills only)

A Cursor plugin derived from `plugins/obsidian-wiki`, so the limit-heavy vault work —
importing AI-coding sessions and ingesting large sources — can run on Cursor's quota
instead of Claude Code's. Both hosts write to the same vault and the same `log.md`;
imports are keyed by session identity, so using both is safe as long as you do not run
`/wiki-ingest` on the same source in both at once.

## Install

```bash
bash ports/cursor/install.sh
```

Copies `ports/cursor/obsidian-wiki/` to `~/.cursor/plugins/local/obsidian-wiki/` with
`rsync --delete`. Re-run after every re-port. It never touches `~/.cursor/hooks.json`.

Use it from a Cursor session opened on the vault (or any project): `/wiki-ingest <source>`,
`/wiki-import-session <path-or-short-id>`, `/wiki-scan-sessions cursor 3`, `/wiki-ask <question>`,
`/wiki-related <page>`.

## Names carry a `wiki-` prefix

Cursor's compatibility loader also reads the **Claude Code plugin cache**
(`~/.claude/plugins/cache/obsidian-wiki/…/skills/`), so an unprefixed `ingest` here collides
with the Claude Code copy and Cursor served the cache copy, measured 2026-09-01 with the
Cursor CLI. The prefix is what makes the port the copy that runs. Invoke as `/wiki-ingest`,
`/wiki-import-session`, `/wiki-scan-sessions`, `/wiki-ask`, `/wiki-related`; the subagents
are `wiki-vault-writer` and `wiki-vault-scanner`.

## What is ported

| Kind | Name | Notes |
|---|---|---|
| skill | `wiki-ingest` | delegates page drafting to `wiki-vault-writer` |
| skill | `wiki-import-session` | delegates extraction to `wiki-vault-writer` |
| skill | `wiki-scan-sessions` | reads the shared `sessions-index.json`; refreshes it with one fixed indexer command if stale |
| skill | `wiki-ask` | vault Q&A with citations |
| skill | `wiki-related` | link suggestions for a page |
| agent | `wiki-vault-writer` | writable, no model pin |
| agent | `wiki-vault-scanner` | `readonly: true`, no model pin |
| scripts | `build-index.py`, `build-worklist.py`, `index-sessions.py`, `resolve-vault.sh`, `score-session.py`, `triage-worklist.py`, `validate*.sh`, `lib/findings.sh` | byte-identical copies of `plugins/obsidian-wiki/scripts/` |

## What is deliberately NOT ported

- **Hooks and everything they drive:** `hooks.json`, session capture on exit, the
  auto-import queue and its drain, the daily Cursor/Codex import job, the daily index
  rebuild, the update check, the vault-path publisher, the statusline snippet, and the
  `index-sessions.sh` daily-gated wrapper with `lib/queue.sh` / `lib/daily-gate.sh`.
  Claude Code keeps all of that; it already indexes Cursor's own session store.
- **`update`** (manages the Claude Code marketplace checkout) and **`review-captures`**
  (works the hook-fed capture queue).
- **`commands/`**: Cursor treats commands as deprecated, and every command here wraps a
  skill of the same name, so `/wiki-ingest` invokes the ported skill directly.
- `lint`, `index`, `merge`, `gaps`, `rebuild-home`, `tag`, `stats`, `log`,
  `vault-schema-maintain` — not needed for the import/ingest workload. Port them the same
  way if you want them.

## Conversion rules

Follows `~/dev/ai-tools/engineering-skills/docs/cursor-conversion-spec.md`:
`.claude-plugin/` → `.cursor-plugin/`, `allowed-tools:` dropped, `${CLAUDE_PLUGIN_ROOT}`
→ paths relative to the plugin install dir, agents lose `tools:` / `model:` (read-only
agents get `readonly: true`), the hook-published vault path becomes
`default_vault` in `~/.config/obsidian-wiki/config.json`, `/obsidian-wiki:x` → `/x`,
Agent-tool `subagent_type` dispatch becomes "delegate to the `<name>` Cursor subagent".

**Do not hand-edit skill or agent bodies here.** Fix upstream in `plugins/obsidian-wiki`
and re-port. Scripts must stay byte-identical to upstream (this project's DEC-002).

## Why the port lives in this repo

engineering-skills' Cursor drift gate is pinned to the coder-plugins marketplace as its
only upstream. Teaching it a second source was a bigger job than this port, so this port
is self-contained here and is not covered by that gate.
