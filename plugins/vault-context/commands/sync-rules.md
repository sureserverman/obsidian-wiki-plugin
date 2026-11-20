---
description: Copy the vault's stack pages to where Claude Code, Cursor and Codex get them
argument-hint: "[--check] [--only <slug>] [--host claude|cursor|codex|all] [--project <dir>|--all-projects]"
allowed-tools: Bash(python3:*)
---

Generate, update and remove the stack copies: one `vault-stack-<slug>.md` in
`${CLAUDE_CONFIG_DIR:-~/.claude}/vault-stacks` for each `<vault>/Portfolio/stacks/<slug>.md`.
At session start, resume, `/clear` and compaction, vault-context's stack hook adds each
copy whose `paths` match a file the project holds to the session. The sync also removes
a marked copy that vault-context 0.6 left in `${CLAUDE_CONFIG_DIR:-~/.claude}/rules`,
which Claude Code would otherwise load a second time.

With `--host cursor` it writes `.cursor/rules/vault-stack-<slug>.mdc` (Cursor's
`globs` rule) into each project where the stack applies — `--project <dir>` for one,
`--all-projects` for every registered project. With `--host codex` it writes
`vault-stack` copies to `${CODEX_HOME:-~/.codex}/vault-stacks/<slug>.md` and one
pointer block, telling Codex to read the copy before touching a matching file, in the
home AGENTS file Codex reads. `--host all` does the three.

**Arguments**: `$ARGUMENTS` — passed through. `--check` compares without writing;
`--only <slug>` limits a Claude-only run to one page; `--host` picks the host
(default `claude`); `--project <dir>` / `--all-projects` name the projects for Cursor;
`--codex-home <dir>` overrides the Codex home.

## Procedure

1. Run the sync:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sync-stack-rules.py" $ARGUMENTS
   ```

2. Report what it printed, in one or two lines: how many copies it wrote, updated,
   removed (legacy copies in the rules folder included) and left unchanged (or, with
   `--check`, which stacks are `missing`, `stale`, `orphan` or `legacy`).

3. On a non-zero exit, read the stderr lines and report each cause:
   - **"page refused: <page>: <reason>"** (exit 1) — that stack page has a defect (no
     `paths`, an unsupported glob, an unknown frontmatter key, a body over 8,192
     bytes). No copy was written or updated for it; its old copy, if any, stays. The
     other pages were still synced. Fix the page in the vault, then run this again.
   - **"refusing: … has no vault-context marker"** (exit 1) — a file named
     `vault-stack-*.md` in the stacks folder or the Claude rules folder was not written
     by this tool. Nothing at all was written. The user renames or removes it; never delete it yourself.
   - **`--check` lines `missing:`, `stale:`, `orphan:`, `legacy:`** (exit 1) — drift; run
     `/vault-context:sync-rules` without `--check`. A refused page or a foreign file
     also makes `--check` exit 1; running without it does not clear those.
   - **"vault not reachable"** (exit 2) — the vault is not mounted or not configured.
     Every existing copy was left in place.
   - **"vault not reachable or empty: no stack pages in …"** (exit 2) — the vault
     shows no stack pages while generated copies exist, so nothing was removed. Most
     often the vault is not mounted: check that first. Only if the owner really deleted
     every page do they remove the leftover `vault-stack-*.md` files by hand.
   - **"file-system error"** (exit 2) — a copy could not be read or written. Copies
     written before the error stay updated; run again once the folder is writable.
   - **"cursor: … would be committed"** (exit 1) — that project does not ignore
     `.cursor/` (or tracks it), so no rule was written there; the other projects were
     still synced. The user adds `.cursor/` to the project's `.gitignore`.
   - **"cursor: … area directory" / missing folder** — skipped, with a line; not an error.
   - **"codex: refusing: <file>: <reason>"** (exit 1) — the Codex AGENTS file holds a
     broken block (a start marker without an end, two blocks) or `vault-stacks/` holds
     a file without the marker. Nothing in the Codex home was written. The user fixes
     the file; never edit it yourself.
   - **usage** (exit 2) — an unsupported `--host`, a `--only` value that is not a slug,
     `--only` with a host other than `claude`, or `--host cursor`/`all` without
     `--project` or `--all-projects`.

Only files carrying the `vault-context:stack-rule` marker are changed or removed — in
the stacks folder, the Claude rules folder, a project's `.cursor/rules/` and the
Codex `vault-stacks/` folder — plus the text between the
`vault-context:stacks:start` / `:end` comments in the Codex AGENTS file, whose other
bytes are kept. The vault is never modified.

**Examples**:
- `/vault-context:sync-rules` — bring every stack copy in step with the vault
- `/vault-context:sync-rules --check` — report drift, write nothing
- `/vault-context:sync-rules --host all --all-projects` — Claude Code, Cursor in every
  registered project, and Codex
