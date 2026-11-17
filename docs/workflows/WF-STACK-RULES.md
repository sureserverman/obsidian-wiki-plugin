# WF-STACK-RULES — Vault stack pages reach Claude Code as path-scoped rules

An owner keeps one copy of a file-keyed fact (how this stack's files are laid out,
which command validates them) as a stack page in the vault. vault-context turns each
page into a Claude Code rule that loads when a matching file is touched, and names
the applying stacks in each project's sidecar.

## Steps

- **WF-STACK-RULES-001 — The page.** A stack page is `<vault>/Portfolio/stacks/<slug>.md`.
  Its frontmatter holds exactly `stack` (the slug, equal to the file stem), `paths`
  (globs: `**`, `*`, `?`, `{a,b}`), `sources` (absolute paths the facts were read
  from), optional `related` (wiki page titles) and `checked` (a date). The body is
  at most 8,192 bytes. vault-context never writes it; the owner or a plan does.
- **WF-STACK-RULES-002 — The sync.** `/vault-context:sync-rules`
  (`scripts/sync-stack-rules.py`) writes `vault-stack-<slug>.md` into
  `${CLAUDE_CONFIG_DIR:-~/.claude}/rules`: frontmatter holding only `paths`, the
  marker comment `vault-context:stack-rule source=<slug> sha256=<page sha256>`, then
  the page body byte for byte. It updates a rule whose page changed and removes a
  rule whose page is gone. It prints how many it wrote, updated, removed and left.
- **WF-STACK-RULES-003 — The load.** Claude Code loads a rule the first time a file
  matching its `paths` is read, written or edited in a session
  (`InstructionsLoaded`, `load_reason: path_glob_match`).
  `tests/live/stack_rule_loads.sh <slug> <sample>` proves it for one rule.
- **WF-STACK-RULES-004 — The sidecar.** `/vault-context:link` and `:refresh` add a
  `## Stack rules` block between `vault-context:stacks:start` / `:end` comments,
  naming each stack whose `paths` match a file the project tracks, its globs, its
  page and its related wiki pages. No stack applies → no block.
- **WF-STACK-RULES-005 — The nudge.** At session start, when neither the link nor
  the refresh nudge fired and `sync-stack-rules.py --check` reports drift, the hook
  prints one line: "Stack rules are out of date with the vault. Run
  /vault-context:sync-rules." It never runs the sync itself.
- **WF-STACK-RULES-006 — The lane.** `validate-stacks.sh` reports `stack-rule-stale`,
  `stack-rule-missing`, `stack-source-missing` (warn), `stack-page-invalid` and
  `stack-rule-foreign` (error) from the same `--check --lint --json` output.

## Invariants

- **WF-STACK-RULES-INV-1 — vault-context never writes to the vault** (W DEC-003).
  The sync reads pages; only the rules folder is written.
- **WF-STACK-RULES-INV-2 — Only marked files are changed or removed.** A
  `vault-stack-*.md` without the marker, a symlink, or a marker naming another slug
  stops a write run before anything is written, and is left untouched.
- **WF-STACK-RULES-INV-3 — A missing vault removes nothing.** No vault → exit 2.
  A vault showing no stack pages while generated rules exist → exit 2, nothing removed.
- **WF-STACK-RULES-INV-4 — A page that cannot be parsed is refused, never guessed at**
  (W DEC-002): named with its reason; no rule is written or updated for it.
- **WF-STACK-RULES-INV-5 — The hook never modifies a file.**
