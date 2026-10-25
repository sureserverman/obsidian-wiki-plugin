# `scan` — first-run seeding and drift detection

The procedure behind `../SKILL.md` § `scan`: load the registry, detect drift, and seed it on
first run. In the default flow this is step 1: surface drift, and update the registry only on
the user's typed `--write`.

The command runs `../scripts/portfolio-scan.py`, which walks the tree, reports drift and makes
the registry edits; this skill presents the report and names the next command. Inputs, passed
straight through: `--root <projects-root>` (repeatable), `--json`, `--add <path>` (repeatable),
`--add-all`, `--remove <path>` (repeatable) and `--write` (off by default: the edits are shown
as `would add` / `would remove` and nothing is persisted). `--json` reports drift only:
combined with `--add`, `--add-all` or `--remove` it is a usage error (exit 2).

Operation:

1. **Find the registry.** The script reads the path `_config.py` resolves (format in
   `registry-format.md`) and validates an existing one with the same validator every script
   uses. A registry that cannot be used is refused (exit 2), never read as empty.
2. **Walk.** The projects roots are `--root` when given, else the folder two levels above each
   registered `path` (`<projects-root>/<area>/<name>`). A derived root that is `/`, the home
   folder, or fewer than three folders deep is refused with "pass --root" (exit 2): walking it
   would sweep a whole disk or home. Under each, to a depth of four, a
   directory is a project root if any of these exists beneath it:
   1. a `docs/plans/` directory (plans written into the repo);
   2. a `docs/backlog.md` file (the deferred-work register);
   3. a `.claude/vault-context.md` file (the repo was linked to the vault by
      `/vault-context:link`: a strong "this is a real project I track" signal even before any
      plan exists).

   Symlinked directories are not followed. The parent of `docs` or of `.claude` is the project
   root, deduplicated by real path. Its `area` and `name` are the ones `records-home.py` derives
   for the same repo: the real path's parent folder and last folder, as written. So an entry
   `scan` adds resolves to the same home the resolver named before it was registered. A root
   that is the projects root itself, or whose folders are not one folder name each, is listed
   as not addable.
3. **Report drift**, on every run: `found not in registry` and `registered but missing on
   disk`. The header prints even when both lists are empty, so the user knows the check
   happened. Disabled entries count as registered. Each found root is checked against the
   containment rule `records-home.py --for-write` uses; one that fails it (a grouping folder,
   or a directory that is neither a git repo nor registered) is marked `not addable` with the
   reason, and `--add` refuses it.
4. **Present and ask.** For each drifted entry, ask: add (new), remove (missing), or skip. Then
   name the command line that does what the user chose, for them to type, for example
   `/vault-portfolio:portfolio scan --add <path> --remove <path> --write`.
5. **The edits**, only with `--write`. Removals run first, then additions, each against the
   registry as it stands. An addition is `records-home.py`'s own append (`path`, `name`,
   `area`, `enabled: true`, `added`), under the registry lock, keeping the old bytes as a
   prefix; when another writer registered the repo meanwhile, nothing is appended and that is
   reported. A removal takes out exactly that one entry's lines. A dry run makes the same
   checks, so an edit that `--write` would refuse is reported as refused. Neither rewrites the file
   whole; an edit that cannot be made that way, or that would remove the only entry, is
   refused with what to change by hand. `--write` needs a configured, reachable vault and is
   refused while another owner holds its maintenance window. Any refused edit makes the exit
   status 1.

**First-run flow**, when the registry does not exist: there is nothing to derive a projects
root from, so the script exits 2 unless `--root` is given. With it, the report lists every
candidate. Present the list for pruning, then name the command that seeds it:
`scan --root <projects-root> --add-all --write`, or `--add <path>` per kept candidate. That
creates the registry. **This is the only write `scan` performs during first run.** No project
files are touched and no roll-ups are built. Then exit; the user re-invokes `portfolio` (or one
subcommand) for the actual work.

Drift reporting is the guard against a registry that quietly rots: every default-flow run
surfaces it before doing anything else.

A grouping folder (a directory that holds projects rather than being one) is not a project.
`records-home.py --for-write` refuses to register one, and `scan --add` refuses it by the same
check.
