# `maturity` — the per-project audit, and why the default flow gates it

The procedure behind `../SKILL.md` § `maturity`: audit each project's MATURITY.md and surface
staleness. In the default flow this is step 3, and it runs only when `--include-maturity` is
set. The axes, their auto-detect rules and the ship-ready thresholds belong to planning's
`project-maturity` skill and its own references; this skill does not restate them.

No script implements `maturity`. The command runs `../scripts/_config.py`, whose JSON names the
vault and the registry, then `records-home.py --all-homes`, whose JSON lists every registry
project with its home. This skill dispatches planning's `project-maturity` skill. Inputs:
optional `--project <abs-path>`, optional `--init-missing` (off by default; when set, a project
with no MATURITY.md gets `project-maturity init` instead of being skipped).

Operation:

1. Take the projects from the `--all-homes` JSON: `enabled` ones only, narrowed by `--project`
   (matched against `path`) when given. Each project's home is its `home` field; never derive
   one. A project whose `home` is `null` (a `records: repo` entry, or an entry the resolver
   refuses) is skipped and listed with its `reason`. When `--all-homes` exits non-zero (3: the
   vault is not configured; 2: it is unreachable, or a config file or the registry does not
   parse), report its stderr and stop. With no rows (no registry yet), name
   `$vault-portfolio:portfolio scan` and stop.
2. For each project, dispatch a sub-agent (at most 8 in flight), handing it the project's
   `path` and `home`, that runs `project-maturity`'s `audit` subcommand with `--write`, then
   `get --format json` for the parsed state the roll-up needs.
3. Aggregate and report:
   - one audit summary line per project;
   - every stale manual claim (older than 90 days) across all projects, as
     `project: axis: item: claim-date`;
   - every project with a `[?] stale-detector` marker. These block ship-ready and warrant a
     look.
4. Ask the user, per project, whether to refresh or keep each stale claim.

`global-maturity.md` is not written here; `rebuild` renders it from the MATURITY.md files.

## Why the default flow gates this step

`--init-missing` and the gate exist for the same reason. Skipping projects without a
MATURITY.md keeps a first portfolio run from becoming "scaffold thirty maturity files at
once", and leaving maturity out of the default flow keeps that flow from putting a wall of
unfilled checklist scaffolds in front of the user. So:

- `portfolio maturity` (explicit subcommand invocation) works normally.
- `portfolio` (default flow) skips the maturity step UNLESS `--include-maturity` is passed.

When the checklists are filled across the portfolio, dropping the gate is a change to
`../SKILL.md` § Default flow and § Staged rollout together; `--include-maturity` then
becomes a no-op.
