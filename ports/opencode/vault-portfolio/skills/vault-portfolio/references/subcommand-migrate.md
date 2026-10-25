# `migrate` — the one-time repo → vault move

The procedure behind `../SKILL.md` § `migrate`: move a project's operational docs from its repo
into the vault, once. The trunk states the safety property (copy → verify → delete,
all-or-nothing); this file is the steps.

Inputs: `--project <abs-path>` (one registered, enabled project; an unmatched path is refused
with `not in registry: …`, and a path registered with `enabled: false` with `disabled in the
registry: …`, and a `records: repo` entry with `opted out in the registry: …`, each
non-zero and before any write) or `--all` (every enabled project, skipping `records: repo`
entries, which have no vault home); `--write` (off by default:
dry-run prints the plan and moves nothing). `--write` is refused while another owner holds the
vault's maintenance window.

It moves `<repo>/docs/plans/**/*.md`, `<repo>/docs/backlog.md` and `<repo>/docs/MATURITY.md`
into `<vault>/Portfolio/<area>/<name>/`. The vault is not under version control, so this is a
filesystem move with a verification gate: never `git mv`, never a bare `mv`.

**The command runs the shipped tool; never hand-execute the copy → verify → delete sequence.**
`../scripts/portfolio-migrate.py (--project <abs-path> | --all) [--write]`, with `--write` only
when the user typed it, implements the per-project procedure end to end: the preflight skips, the sha256 gate and its
abort path, the `git rm` or plain `rm` choice, the sidecar line and the `repo:` evidence
rewrite. The numbered steps are that script's contract. Read them to check a run, not to
reproduce it by hand, where a half-finished delete has no undo.

Per-project procedure (all-or-nothing):

1. Build the migrate set: every `*.md` under `docs/plans/`, recursively, keeping its
   subdirectory under the vault `plans/` (a plan set nested in a subdirectory moves too);
   `docs/backlog.md`, or, when there is none, a `backlog.md` kept directly in `docs/plans/`,
   which moves to `<home>/backlog.md` rather than into `plans/`; and `docs/MATURITY.md`. An
   empty set is SKIPPED with `nothing to migrate`.
2. **Preflight the project:**
   - If the home already holds `plans/`, `backlog.md` or `MATURITY.md`, SKIP with
     `vault home already populated; resolve manually`. Never overwrite or merge.
   - **Dirty guard:** SKIP when a file of the migrate set shows in `git status --porcelain` with
     any code other than `??`, that is, a tracked file with uncommitted or staged changes.
     Those edits have no committed copy to fall back on. *Untracked* files (`??`, such as a
     freshly generated `MATURITY.md`) migrate: their content moves to the vault and nothing
     committed is lost.
   - **Non-git repos** still migrate, but step 5 uses plain `rm` and the report flags
     `[no-git-fallback]`: the vault copy is then the *only* copy, and the copy → verify gate
     is the sole safety net. Acceptable for scratch repos, and shown so the user knows.
3. **Re-check the vault**, then **COPY** each source file to its destination. If
   `<vault>/Portfolio/` has disappeared since the run started (a mount dropping mid-run), the
   project FAILS and nothing is written for it, rather than the copy rebuilding a phantom tree.
4. **VERIFY**: for every copied file, `sha256(source) == sha256(destination)`. This is the
   load-bearing gate: on a network-backed vault a truncated write is the realistic failure.
   Any mismatch or error aborts this project, deletes the partial vault copies, leaves the repo
   untouched, and reports it.
5. Only after ALL files verify, remove the sources from the repo: `git rm` in a git work tree,
   falling back to plain `rm` when `git rm` fails (an ignored or untracked file) or when there
   is no git. The repo source is the **last** thing removed.
6. Remove `docs/plans/` if it is now empty, then `docs/` if that is empty. Anything else in
   `docs/` stays. **No tombstone**: the sidecar is the only pointer left in the repo.
7. Write or refresh the repo sidecar's `PORTFOLIO-STATUS` block with the `**Home:**` line
   (`sidecar-format.md`). `rebuild` fills in the rest of the block later.
8. Rewrite the migrated `MATURITY.md`'s `[x] auto:` evidence to `[x] auto:repo:` (the evidence
   points at repo files, now read from a checklist in the vault). Lines already carrying a
   scope prefix, `repo:` or `portfolio:`, are left alone.

Dry-run prints, per project, the file count, the target and the destination list, and flags
skips; it moves nothing. The report is one line per project (`[OK  ]`, `[DRY ]`, `[SKIP]` or
`[FAIL]`) and a summary, `WRITE summary: migrated=N dry=N skipped=N failed=N`. The exit status
is 1 when any project failed.

A re-run writes nothing: an emptied `docs/` gives an empty migrate set, and a repopulated one
meets the populated-home preflight.

**Rollback** (per project): copy the home's docs back to `<repo>/docs/` and restore the repo
deletion from git (`git checkout` or `git restore`), where the files were tracked. That works
because the vault keeps the files and the repo's git keeps the deletions. A file that was never
committed has only the vault copy, which is why the verify gate comes first.
