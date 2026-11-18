# WF-STACK-RULES — Vault stack pages reach Claude Code at session start

An owner keeps one copy of a file-keyed fact (how this stack's files are laid out,
which command validates them) as a stack page in the vault. vault-context copies each
page to a local stacks folder, adds the copies that apply to a project to every
session opened there, and names the applying stacks in each project's sidecar.

## Steps

- **WF-STACK-RULES-001 — The page.** A stack page is `<vault>/Portfolio/stacks/<slug>.md`.
  Its frontmatter holds exactly `stack` (the slug, equal to the file stem), `paths`
  (globs: `**`, `*`, `?`, `{a,b}`), `sources` (absolute paths the facts were read
  from), optional `related` (wiki page titles) and the required `checked` (a date). The body is
  at most 8,192 bytes. vault-context never writes it; the owner or a plan does.
- **WF-STACK-RULES-002 — The sync.** `/vault-context:sync-rules`
  (`scripts/sync-stack-rules.py`) writes `vault-stack-<slug>.md` into the stacks
  folder, `${CLAUDE_CONFIG_DIR:-~/.claude}/vault-stacks` (`--stacks-dir`, else
  `$VAULT_CONTEXT_STACKS_DIR`): frontmatter holding only `paths`, the marker comment
  `vault-context:stack-rule source=<slug> sha256=<page sha256>`, then the page body
  byte for byte. It updates a copy whose page changed and removes a copy whose page is
  gone. It also removes a marked `vault-stack-*.md` left in
  `${CLAUDE_CONFIG_DIR:-~/.claude}/rules` by vault-context 0.6, which Claude Code would
  load a second time; `--check` reports one as drift `legacy`. It prints how many it
  wrote, updated, removed (legacy copies included) and left.
- **WF-STACK-RULES-003 — The load.** At session start, resume, fork, `/clear` and
  compaction, the SessionStart hook `scripts/stack-context.py` takes the project root
  (the git top level of the input `cwd`, else `cwd`) and, for each marked copy in the
  stacks folder in slug order, decides with `lib/stack_pages.py` (`project_files`,
  `applies`) whether its `paths` match a project file. It prints one
  `hookSpecificOutput` object (`hookEventName: SessionStart`) whose
  `additionalContext` holds each applying copy whole, marker line included, up to
  9,500 characters in all; a copy that does not fit is named in one line with its
  path. No applying copy → no output. It reads only local files, writes nothing, and
  on any error prints nothing and exits 0.
  `tests/live/stack_page_loads.sh <slug> <sample> [--plugin-dir DIR]` proves it in a
  real headless session (`LOADED session_start_hook`).
- **WF-STACK-RULES-004 — The sidecar.** `/vault-context:link` and `:refresh` add a
  `## Stack rules` block between `vault-context:stacks:start` / `:end` comments,
  naming each stack whose `paths` match a file the project tracks, its globs, its
  page and its related wiki pages. No stack applies → no block.
- **WF-STACK-RULES-005 — The nudge.** At session start, when neither the link nor
  the refresh nudge fired and `sync-stack-rules.py --check` reports drift (`missing`,
  `stale`, `orphan` or `legacy`), the nudge hook (`scripts/session-start.sh`)
  prints one line: "Stack rules are out of date with the vault. Run
  /vault-context:sync-rules." It never runs the sync itself.
  `VAULT_CONTEXT_NO_STALENESS_NUDGE=1` silences the refresh nudge only.
- **WF-STACK-RULES-006 — The lane.** `validate-stacks.sh` reports `stack-rule-stale`,
  `stack-rule-missing`, `stack-source-missing` (warn), `stack-page-invalid` and
  `stack-rule-foreign` (error) from the same `--check --lint --json` output, and
  `stack-sync-error` (error) when that output is not JSON.

## Invariants

- **WF-STACK-RULES-INV-1 — vault-context never writes to the vault** (W DEC-003).
  The sync reads pages; only the stacks folder is written, and a marked legacy copy
  in the Claude rules folder removed. The stack hook never reads the vault.
- **WF-STACK-RULES-INV-2 — Only marked files are changed or removed.** A
  `vault-stack-*.md` without the marker, a symlink, or a marker naming another slug,
  in the stacks folder or the Claude rules folder, stops every mode before anything is
  written, and is left untouched. The stack hook adds only marked copies.
- **WF-STACK-RULES-INV-3 — A missing vault removes nothing.** No vault → exit 2.
  A vault showing no stack pages while generated or legacy copies exist → exit 2,
  nothing removed.
- **WF-STACK-RULES-INV-4 — A page that cannot be parsed is refused, never guessed at**
  (W DEC-002): named with its reason; no copy is written or updated for it.
- **WF-STACK-RULES-INV-5 — Neither hook modifies a file.**
