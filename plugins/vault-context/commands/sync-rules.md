---
description: Turn the vault's stack pages into Claude Code path-scoped rules
argument-hint: "[--check] [--only <slug>]"
allowed-tools: Bash(python3:*)
---

Generate, update and remove the stack rules: one `vault-stack-<slug>.md` in the user's
Claude rules folder for each `<vault>/Portfolio/stacks/<slug>.md`. Claude Code loads a
rule when a file matching its `paths` is read, written or edited.

**Arguments**: `$ARGUMENTS` — passed through. `--check` compares without writing;
`--only <slug>` limits the run to one page.

## Procedure

1. Run the sync:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sync-stack-rules.py" $ARGUMENTS
   ```

2. Report what it printed, in one or two lines: how many rules it wrote, updated,
   removed and left unchanged (or, with `--check`, which stacks are `missing`, `stale`
   or `orphan`).

3. On a non-zero exit, say why and what fixes it:
   - **exit 1, "page refused"** — the named stack page has a defect (no `paths`, an
     unsupported glob, an unknown frontmatter key, a body over 8,192 bytes). Nothing
     was written for that page. Fix the page in the vault, then run this again.
   - **exit 1, "refusing: … has no vault-context marker"** — a file named
     `vault-stack-*.md` in the rules folder was not written by this tool. Nothing was
     written. The user renames or removes it; never delete it yourself.
   - **exit 1 under `--check`** — drift; run `/vault-context:sync-rules` without it.
   - **exit 2, "vault not reachable"** — the vault is not mounted or not configured.
     Every existing rule was left in place.

Only the rules folder is written, and only files carrying the
`vault-context:stack-rule` marker. The vault is never modified.

**Examples**:
- `/vault-context:sync-rules` — bring every stack rule in step with the vault
- `/vault-context:sync-rules --check` — report drift, write nothing
