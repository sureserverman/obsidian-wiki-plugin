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

3. On a non-zero exit, read the stderr lines and report each cause:
   - **"page refused: <page>: <reason>"** (exit 1) — that stack page has a defect (no
     `paths`, an unsupported glob, an unknown frontmatter key, a body over 8,192
     bytes). No rule was written or updated for it; its old rule, if any, stays. The
     other pages were still synced. Fix the page in the vault, then run this again.
   - **"refusing: … has no vault-context marker"** (exit 1) — a file named
     `vault-stack-*.md` in the rules folder was not written by this tool. Nothing at
     all was written. The user renames or removes it; never delete it yourself.
   - **`--check` lines `missing:`, `stale:`, `orphan:`** (exit 1) — drift; run
     `/vault-context:sync-rules` without `--check`. A refused page or a foreign file
     also makes `--check` exit 1; running without it does not clear those.
   - **"vault not reachable"** (exit 2) — the vault is not mounted or not configured.
     Every existing rule was left in place.
   - **"vault not reachable or empty: no stack pages in …"** (exit 2) — the vault
     shows no stack pages while generated rules exist, so nothing was removed. Most
     often the vault is not mounted: check that first. Only if the owner really deleted
     every page do they remove the leftover `vault-stack-*.md` files by hand.
   - **"file-system error"** (exit 2) — a rule could not be read or written. Rules
     written before the error stay updated; run again once the folder is writable.
   - **usage** (exit 2) — an unsupported `--host` or a `--only` value that is not a slug.

Only the rules folder is written, and only files carrying the
`vault-context:stack-rule` marker. The vault is never modified.

**Examples**:
- `/vault-context:sync-rules` — bring every stack rule in step with the vault
- `/vault-context:sync-rules --check` — report drift, write nothing
