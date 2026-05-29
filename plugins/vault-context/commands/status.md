---
description: Show the current project's vault-context status
allowed-tools: Bash(bash:*), Read
---

Report the current project's vault-context status. **Read-only** — does not modify any
file.

**Arguments**: none.

## Procedure

1. **Run the link validator** and parse its JSON — it decides every mechanical part
   of the status (sidecar presence and well-formedness, the CLAUDE.md `@`-import
   block, sidecar↔import drift, circular-link, and index freshness):

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/validate.sh" "$PWD" --json
   ```

   Each finding is `{severity, rule, category, path, line, message}`. The rules you
   may see:

   - `link-circular` (error) — the project sits at or under the vault.
   - `link-sidecar-no-body-markers` / `link-sidecar-no-header` (warn) — the sidecar
     is malformed; suggest `/vault-context:refresh`.
   - `link-import-missing` (warn) — sidecar exists but CLAUDE.md has no import block;
     suggest `/vault-context:link --force`.
   - `link-import-dangling` (warn) — CLAUDE.md imports a sidecar that doesn't exist.
   - `link-import-no-ref` (warn) — markers present but no `@.claude/vault-context.md`.
   - `link-sidecar-stale` / `link-index-stale` (info) — freshness nudges.

   A clean run with no findings means: not linked yet (no sidecar, no import) — or
   linked and healthy. Distinguish the two by whether `.claude/vault-context.md`
   exists.

2. **Read the sidecar header for the human summary.** If `.claude/vault-context.md`
   exists, read its first ~10 lines and extract vault path, generation date, index
   date, and match count — the validator confirms the header is *present*; you read
   it to *report its values*.

## Output

A compact status block grouped as **vault · sidecar · CLAUDE.md import**, not a wall
of text. Report the validator's findings in plain language and attach the matching
suggestion (`/vault-context:link`, `--force`, `/vault-context:refresh`, or
`/vault-context:unlink`). If there are no findings and no sidecar, say "no vault
context for this project yet" and suggest `/vault-context:link`.

This is a **read-only** command. Do not modify any file.

**Examples**:
- `/vault-context:status` — show vault path, sidecar age, match count, import status
