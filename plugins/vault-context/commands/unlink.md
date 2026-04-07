---
description: Remove the vault-context sidecar and CLAUDE.md import from the current project
---

Remove the vault-context sidecar from the current project and delete the delimited
block from project `CLAUDE.md`. Surrounding `CLAUDE.md` content is left untouched.

**Arguments**: none.

This is the **only destructive** command in the `vault-context` plugin. Always confirm
with the user before executing.

## Procedure

1. **Confirm with the user**. Show what will be removed:
   - `<cwd>/.claude/vault-context.md` (the sidecar file)
   - The delimited `<!-- vault-context:start --> ... <!-- vault-context:end -->` block
     inside `<cwd>/CLAUDE.md` (if present)
   Ask "Proceed with unlink? [y/N]".
2. If the user confirms, **delete the sidecar**: `rm <cwd>/.claude/vault-context.md`.
   If `.claude/` is now empty, leave the directory in place — other tools may use it.
3. **Edit project CLAUDE.md** if it exists and contains the delimited block: remove
   only the lines from `<!-- vault-context:start -->` through `<!-- vault-context:end -->`
   inclusive, plus a single trailing blank line if one was inserted by `link`. Do not
   touch any other content.
4. If `CLAUDE.md` was created entirely by `vault-context:link` (only contains the
   delimited block plus the boilerplate header) and would be left effectively empty,
   ask the user whether to delete the file too. Default: keep it.
5. **Report** what was removed and confirm the operation is reversible by re-running
   `/vault-context:link`.

The vault is never modified by this command.

**Examples**:
- `/vault-context:unlink` — remove sidecar and delimited block (with confirmation)
