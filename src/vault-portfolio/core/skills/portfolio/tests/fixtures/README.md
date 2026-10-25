# Portfolio test fixtures

Synthetic data for the portfolio tests. Every name is made up. The projects
live in the areas `apps` and `tools` and are named `example-*`, except three
registers in `decisions/` named for the shape they carry (`malformed-headings`,
`dup-ids`, `orphan-proj`). Each vault tree has its own domain registers:
`mobile`, `network` and `systems` in `decisions/`; `android`, `rust` and
`malformed` in `domain-decisions/`.

**Register ids are written as placeholders.** A decision or backlog id in a
committed file would look like a real register entry, so the files spell them
`{DEC}-007`, `{GDEC}-MOB-003` and `{BL}-001`. A test copies a fixture tree into
its temp directory and expands `{DEC}`, `{GDEC}` and `{BL}` there before using
it (`expand_ids()` in each test). Nothing reads these files in place.

- `decisions/` — a vault tree for the decisions register
  (`test-portfolio-decisions.py`). Three per-project registers under
  `Portfolio/apps/` and two under `Portfolio/tools/`, plus three domain
  registers under `Portfolio/decisions/`. Each file carries one shape on
  purpose: a block missing fields, a superseded entry, wrapped and nested
  field values, mistyped headings, a duplicate id in one file, the same domain
  id in two files, a link to a missing domain entry, a link naming the wrong
  domain file, a one-sided `Applies to`, an unprefixed wikilink, and projects
  that are listed but have no register.

- `domain-decisions/` — a vault tree for the per-domain decisions digest and
  promotion (`test-domain-decisions.py`). Three domain registers under
  `vault/Portfolio/decisions/`: `rust` (an accepted entry and a superseded
  one), `android` (one entry with a `Source`, applying to a project that has no
  register) and `malformed` (a block missing `Reason`, a superseded block and a
  heading that is not an id). Two project registers under
  `vault/Portfolio/apps/`: `example-app` (an entry already promoted, one marked
  `Global: none`, and one not yet promoted) and `example-lib` (one entry not
  yet promoted). The refusal cases add a duplicate domain id and an undated
  project entry to their temp copy only.

- `proj-a-plans-and-backlog/` — a repo with two plans, a backlog and a
  maturity checklist. One plan is all done; the other has two open tasks, a
  gate bullet and one Deferred bullet. The backlog's one entry has the same
  Source as the first open task. Used by `test-portfolio-unify.py` (expected:
  3 candidates, 1 duplicate, 2 new) and by the migrate cases.

- `proj-b-plans-only/` — a repo with one legacy plan (no Status fields) and
  three unchecked bullets, and no backlog. Unify emits three `unchecked-open`
  candidates and creates the backlog.

- `proj-c-bare/` — a repo whose `docs/` holds nothing to move. Migrate skips it.

`../migrate-dryrun.txt` is the dry-run output of `portfolio-migrate.py --all`
over these three repos, registered as `apps/example-app`, `apps/example-cli`
and `apps/example-bare`, with the temp vault path written as `<vault>`.
`test-vault-write-idempotency.py` regenerates it and compares.
