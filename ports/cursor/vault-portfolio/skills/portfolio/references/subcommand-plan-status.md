# `plan-status` — classification order and evidence grades

The procedure behind `../../vault-portfolio/SKILL.md` § `plan-status`: reconcile every vault plan's recorded status
against its real progress. The trunk states what binds every invocation (report-first, the
per-plan confirm, abandonment never inferred); this file is the classification and evidence
detail.

Inputs: optional `--check`, `--json`, `--verbose`, `--fix`, `--restore <run-id>`,
`--vault <dir>`, `--registry <file>`. The command runs `../scripts/plan-status-audit.py` with the
flags the user typed.
**Report-first: the default invocation writes nothing.**

Why it exists: a plan's recorded status and its actual task completion are read by two
different code paths and never reconciled. `unify` emits an in-flight plan's open tasks as
backlog candidates and `compass next` ranks projects by what is in flight, so a plan that is
finished but never closed out is a standing source of phantom work in both.

1. Enumerate every `*.md` under `<vault>/Portfolio/*/*/plans/`, recursively (a plan set in a
   subdirectory counts), skipping `.audit-backups/`. **The vault is the corpus, not the
   registry**: a project with plans in the vault and no registry entry is still classified,
   because skipping it while reporting a portfolio-wide audit would claim coverage the run does
   not have. The registry resolves each project's **repo path** for evidence, nothing more. A
   registered project with no `plans/` directory, and a `plans/` directory that cannot be read,
   are each reported as such rather than as "no plans". A `records: repo` entry keeps its plans
   in its repo: a vault folder at its path gets a row with no files and that reason, and
   nothing in it is classified or offered to `--fix`.
2. Classify each plan, in this order: `abandoned` → `blocked` → `completed` →
   `unclassifiable` → `not-a-plan` → `no-status` → `never-started` → `started-unfinished`.
   Human-authored terminal markers win first, with **one** exception: a plan the vendored
   parser's `plan_blocked()` reports blocked (a `[~]` stage-gate check, or a master whose
   sub-plan is blocked, unless `**Blocked-accepted:**` closes it) classifies `blocked` even when
   it carries `**Completed:**`. The close-out line is the author's claim about the work; the
   gate box is the record of what could not be proven, and proof outranks claim. Nothing after
   `completed` overrules an author.
3. **`unclassifiable`** is the load-bearing class: a plan carrying any bracketed `Status:`
   marker outside the contract's `[ xX~]` (`[!]`, `[~ BLOCKED]`, `[~ N/A]`) has a task
   invisible to the parser, so it reads **more finished than it is**. Those plans are **never
   offered as completion candidates, under any flag.**
4. **`not-a-plan`** is the only class decided by filename (a design, architecture or done
   record living in `plans/`, or a `README.md` or `backlog.md` kept there: the same files
   `unify` and `compass` skip), and only for a file with no task entries and no marker at all.
   Anything written inside the document outranks the filename guess.
5. A **candidate** is a `started-unfinished` plan with every task done and no close-out line.
   Gather **graded** evidence for it, strongest first:
   - **`register+commit`**: a master plan beside it marks this exact plan `[x]` in its
     `## Sub-plans` register *and* names a commit that resolves in the repo. A human, in another
     document, naming the plan and the work. It lives in the **vault**, not in git.
   - **`register`**: the register marks it done but names no commit, or the one it names does
     not resolve. It still identifies *the plan*.
   - **`names-the-plan`**: a commit message names the plan's filename or slug as a whole token,
     so `<plan>.md.orig` does not count.
   - **`correlative`**: commits with a message line starting `Stage N green` or `Stage N gate`, dated on
     or after the plan's filename stamp. These identify a repo and a period, **never a plan**:
     the same commits get offered to every plan that repo ran. An unstamped plan gets none.
   - **`none`**: searched, found nothing. Distinct from "no repo to search", which the report
     states as its own reason.

   Git is never run against the vault, which is not under version control: a repo path inside
   it is refused outright rather than allowed to fail and read as "no evidence". Each candidate
   also shows its **stage-gate state**, because *all tasks `[x]`* is not the same as *finished*:
   a plan can carry every task done and still have an unticked final gate.
6. `--fix` presents one candidate at a time with its evidence and the exact line it would write,
   and requires a per-plan `y`. Before writing it copies the plan to
   `.audit-backups/<run-id>/` in the plan's own directory (never overwriting an existing
   backup), and the write itself is atomic and keeps the file's mode. A symlinked plan is
   refused. `--restore <run-id>` reverts a run wholesale, across the whole vault; the vault has
   no version control behind it, so the backup is the only undo that exists. Without a TTY the
   prompt is skipped and nothing is written. The command's Bash call has none, so `--fix`
   there prints `no tty — skipped` per candidate; to record, the user runs the script line
   with `--fix` in a terminal.
7. The recorded line states the evidence's **grade**:
   `**Completed:** <date> — recorded by plan-status-audit; <detail>`. A correlative match is
   written as `user-confirmed; no commit names this plan — correlated with stage commits
   <hashes>`, never as a bare `evidence: <hashes>`. The line outlives the run by years, and a
   future reader has only its words to tell the two apart.

**It never infers `**Abandoned:**`.** A marker nobody adopts degrades to the status quo; a
heuristic false positive is a *new* failure, because a plan wrongly marked abandoned disappears
from the one view still listing its open work. No banner-prose detector is consulted here.

`--check` runs the **invariants**, which hold for any corpus: every enumerated plan got a class
or was reported unreadable, no plan lands in two classes, and candidates and unclassifiable are
disjoint. They gate the exit status (1 when one fails). It also prints a separately labelled
set of corpus observations, which are **never fatal**: a fact about one vault's contents is not
a defect, and a human legitimately adopting a marker must not turn a green audit red.

`--vault` gets the same reachability check as the configured vault, because this tool writes
backups into whatever tree it is handed. Exit codes: 0 report (and any `--fix` run); 1 a failed
invariant, a `--restore` that restored nothing or failed, or an unset or unreachable configured
vault; 2 an unreachable `--vault`, an
unusable registry, no enabled project, or `--fix` combined with `--json` (which writes nothing).
A write refused by a maintenance window exits non-zero before anything is written.
