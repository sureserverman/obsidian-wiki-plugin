# `unify` — one script over the whole registry

The procedure behind `../SKILL.md` § `unify`: derive backlog candidates for every enabled
project. In the default flow this is step 2: surface candidates per project; on confirm, the
accepted ones land in that project's `backlog.md` in the vault.

**One process, no fan-out.** Walking plan files and comparing `Source` strings is decidable,
and a decidable rule belongs in a script. Asking one agent per project to perform the same
parse in prose gave the rule several definition sites and only one place the answer really
came from. So `../scripts/portfolio-unify.py` does the parse, and the model does the part that
was never mechanical: presenting the candidates and taking the user's decision. The
8-in-flight cap still binds `maturity`, which needs per-project judgment.

Inputs, passed straight through to the script: optional `--project <abs-path>` (one registered
project, matched against the registry `path` after `~` expansion and resolving; an unmatched
path is refused with `not in registry: …` and a path registered with `enabled: false` with
`disabled in the registry: …`, and a `records: repo` entry with `opted out in the registry:
…`, each with a non-zero exit; without `--project`, `records: repo` entries are skipped),
optional `--include-stale`
(default off; also surfaces unresolved items in plans older than 90 days by filename stamp),
optional `--write` (default off).

Operation:

1. The command runs the sweep, `portfolio-unify.py` with the flags the user typed. It loads
   the registry, keeps `enabled` projects, and parses every project's
   `<vault>/Portfolio/<area>/<name>/plans/**/*.md`, skipping `plans/.audit-backups/`, in one
   process. `--project <abs-path>` narrows it and `--include-stale` widens the signal set.
   Without `--write` it is the dry run: step 3 is the confirm, and writing before it would make
   the prompt a formality.

   What counts as a candidate is decided by the vendored plan parser's `parse_plan()`
   (`<vault-portfolio-plugin>/vendor/staged_planning/plan_parser.py`), never restated here:
   - in a plan with `- **Status:**` fields, a task at `[ ]` (`status-unexecuted`) or `[~]`
     (`status-partial`);
   - in a plan without them, an unchecked `- [ ]` bullet in a stage that the repo's git log
     does not mark executed (a commit dated on or after the plan's date stamp that says
     `Stage N`);
   - in both kinds, a bullet under a `## Deferred` / `### Deferred` heading.

   Preflight bullets and stage-gate bullets are never candidates, and neither is anything in
   a file that is not a plan: `*-design.md`, `*-architecture.md`, `*-done.md`, `README.md` or
   `backlog.md` (`portfolio-rebuild.py`'s `not_a_plan()`, which `compass` and `plan-status`
   share). A plan
   carrying `**Abandoned:**` still contributes its open tasks, for human triage.

2. Read its report. It prints one line per project that has candidates, then a total:

   ```
     apps/example-app: 2 new, 1 dup, 3 candidates
     apps/example-cli: 3 new, 0 dup, 3 candidates

   DRY-RUN: 5 new entries, 1 duplicates skipped, 6 candidates across 3 projects
   ```

   Present it as-is rather than re-typing it. A re-typed figure is a figure nobody measured.

3. **Present to the user:** accept all, accept some projects, or skip. The script writes every
   new candidate of each project it is given, so a partial accept is expressed by a run per
   accepted project with `--project`; it cannot pick single candidates inside a project.
   This step is the confirm, and it is the reason a model runs this subcommand at all.

4. On accept, name the command line for the user to type:
   `/vault-portfolio unify --write`, with `--project` per accepted project when the
   user narrowed the set. **Never write during dry-run.** Each new entry is appended as
   `## BL-NNN — <title>` with `Opened`, `Source`, `Reason`, `Next step` and `Tags`
   (`auto-unified`, plus the plan's date stamp). A missing `backlog.md` is created with its
   header. Re-running straight afterwards yields zero new entries: every accepted candidate's
   `Source` now lives in the backlog and matches by exact string equality.
   `--write` is refused while another owner holds the vault's maintenance window.

**Why these rules exist** (both bind from `../SKILL.md` § Hard rules):

- Dry-run is the default. `--write` is the only path to a file change, and even then the
  candidates come from a user-confirmed set; the prompt in step 3 IS the confirm.
- The dedup key is the `Source` string, not the rendered entry, so a re-run on a later date
  still matches. A key that picks up stray whitespace silently misses every match, which is
  why the key is compared stripped.
