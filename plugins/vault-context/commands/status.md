---
description: Show the current project's vault-context status
---

Report the current project's vault-context status. **Read-only** — does not modify any
file.

**Arguments**: none.

## Procedure

1. **Resolve the vault** by running `${CLAUDE_PLUGIN_ROOT}/scripts/resolve-vault.sh`. If
   it exits non-zero, report "no vault configured" and point at the bootstrap step in
   `obsidian-wiki`'s README.
2. **Check the vault index**: stat `<vault>/index.md`. Report whether it exists and
   when it was last modified. If it's more than 30 days old, note that it may be stale
   and suggest `/obsidian-wiki:index` from the vault.
3. **Check the sidecar**: stat `<cwd>/.claude/vault-context.md`. If it doesn't exist,
   report "no vault context for this project yet" and suggest `/vault-context:link`.
   If it does exist, read its header (the first ~10 lines) and extract: vault path,
   generation date, index date, match count.
4. **Check the CLAUDE.md import**: look at `<cwd>/CLAUDE.md` for the
   `<!-- vault-context:start -->` … `<!-- vault-context:end -->` markers. Report
   whether the delimited block is present and points at `.claude/vault-context.md`.
   If the sidecar exists but the import block is missing, that's a drift the user can
   fix by running `/vault-context:link --force`.

Output is a compact status block, not a wall of text. Group it as: vault, sidecar,
CLAUDE.md import.

This is a **read-only** command. Do not modify any file.

**Examples**:
- `/vault-context:status` — show vault path, sidecar age, match count, import status
