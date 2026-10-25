# Hand tests for the portfolio skill

The automated tests (`test-*.py` here, run by the marketplace's `tests/test_vault_portfolio.sh`)
cover every script. What they cannot cover is the command and the skill: whether
`/vault-portfolio:portfolio` runs the right script, and whether a model following `../SKILL.md`
stops at the confirm, names the `--write` line for the user to type, and reports what the
script printed.
This file is that check, done by hand against a throwaway setup. Nothing here touches a real
vault or registry.

Each section lists the commands, what to look for, and the lesson the check exists for. Record a
run by appending a dated line under **Runs** at the end: what was run, pass or fail, and any
deviation.

## Setup: a throwaway home, vault and registry

```bash
T=$(mktemp -d)
mkdir -p "$T/vault/Portfolio" "$T/.config/obsidian-wiki" "$T/dev/apps"
F=<plugin root>/skills/portfolio/tests/fixtures
cp -r "$F/proj-a-plans-and-backlog" "$T/dev/apps/example-app"
cp -r "$F/proj-b-plans-only"        "$T/dev/apps/example-cli"
cp -r "$F/proj-c-bare"              "$T/dev/apps/example-bare"
# Fixture register ids are {BL}/{DEC}/{GDEC} placeholders; expand them in the copy.
grep -rl '{BL}\|{DEC}\|{GDEC}' "$T/dev" | xargs -r sed -i 's/{BL}/BL/g; s/{DEC}/DEC/g; s/{GDEC}/GDEC/g'
printf '{"default_vault": "%s"}\n' "$T/vault" > "$T/.config/obsidian-wiki/config.json"
export HOME="$T"
unset OBSIDIAN_VAULT_PATH BUSINESS_SCAN_PATH
```

`python3 <plugin root>/skills/portfolio/scripts/_config.py` must print `$T/vault` as the vault
and `$T/.config/obsidian-wiki/projects-registry.yaml` as the registry before going on.

## 1. `scan` first run seeds the registry and exits

`git init` each fixture copy first: the containment rule adds only a git repo or a registered
path. Run `/vault-portfolio:portfolio scan --root $T/dev`. The line carries arguments, so
Claude Code asks permission before it runs; approve it once, not for the session.

- The walk finds `apps/example-app` and `apps/example-cli` (they hold `docs/plans/` or
  `docs/backlog.md`) and not `apps/example-bare`, whose `docs/` holds no marker. Register
  `apps/example-bare` by hand afterwards, so step 3 has a project to skip.
- The model presents the candidates and names `scan --root $T/dev --add-all --write` (or
  `--add` per kept candidate); the registry appears only when that line is typed.
- It then **exits**: no backlog, maturity file or roll-up appears.

Lesson: the first run must touch nothing but the registry, and a candidate list is a question,
not a write.

## 2. `scan` again reports drift, even when there is none

Re-run `/vault-portfolio:portfolio scan`. The report prints a drift header with both lists
empty. Add `$T/dev/apps/example-new/docs/backlog.md` (and `git init` it) and re-run: it shows
up under `found not in registry`, and the registry changes only on a typed `--add … --write`.

## 3. `migrate` dry run, then write, then a no-op re-run

```bash
python3 <plugin root>/skills/portfolio/scripts/portfolio-migrate.py --all
python3 <plugin root>/skills/portfolio/scripts/portfolio-migrate.py --all --write
python3 <plugin root>/skills/portfolio/scripts/portfolio-migrate.py --all --write
```

- The dry run lists files and targets and moves nothing; compare it with
  `migrate-dryrun.txt` (the vault path written as `<vault>`).
- The write copies, verifies by sha256, then deletes the sources; each repo's sidecar gains a
  `PORTFOLIO-STATUS` block with the `Home` line.
- The second write migrates nothing: every project is skipped.
- Move a migrated home's `backlog.md` aside, put a `docs/backlog.md` back in the repo, and run
  again: the project is skipped as `vault home already populated` because `plans/` is still
  there. Nothing is merged.

Lessons: a re-run is a no-op because of two guards (an emptied `docs/`, and the populated-home
preflight), and a nested plan directory must migrate too, which is why the plan glob is
recursive.

## 4. `unify` presents, then writes only what was accepted

Run `/vault-portfolio:portfolio unify`.

- The command runs the script without `--write`; the model shows its report as printed, not
  retyped.
- It asks: accept all, accept some projects, or skip.
- Accept one project only. The model names `unify --write --project <that repo>` and runs
  nothing itself; type it, and only that project's backlog changes.
- Re-run the dry run: the accepted project shows 0 new.

Lesson: a fixture's backlog `Source` must name the directory the fixture plans really live in,
or the dedup case never runs and the test passes without testing anything. The dedup key is
compared stripped, because a key carrying trailing whitespace misses every match and doubles
the backlog on each run.

## 5. `rebuild` writes once, then writes nothing

```bash
python3 <plugin root>/skills/portfolio/scripts/portfolio-rebuild.py --write
python3 <plugin root>/skills/portfolio/scripts/portfolio-rebuild.py --write
```

- The first run reports sidecars enriched and the roll-ups written.
- The second reports `sidecars enriched: 0` and every roll-up `False`; `sha256sum` of every
  file under `$T/vault/Portfolio` is unchanged.
- Paste a second PRESERVE pair into `global-backlog.md` and run again: the report says
  `SKIPPED (ambiguous PRESERVE)` and that file is byte-identical; the other roll-ups still run.
- The business status reads `business layer: unavailable (no business_scan configured)`.

## 6. An unmounted vault is refused, not built

```bash
mkdir -p "$T/empty-mount"
OBSIDIAN_VAULT_PATH="$T/empty-mount" python3 <plugin root>/skills/portfolio/scripts/portfolio-migrate.py --all --write
```

The run exits non-zero with `vault unreachable: … has no Portfolio/`, and `$T/empty-mount`
stays empty.

Lesson: an existence check cannot tell an unmounted mountpoint from a vault, because a
mountpoint is a directory either way. Without the `Portfolio/` check, a migrate builds a
phantom tree there and moves a repo's only docs into it.

## 7. `integrate` reports an asymmetry and never fixes it

Write `$T/vault/Portfolio/apps/example-app/integration.md` declaring
`impacts: [{target: "[[example-cli]]", why: test}]` and nothing on the other side. Run
`/vault-portfolio:portfolio integrate`: the asymmetry is listed, the model suggests editing one
side, and neither `integration.md` changes.

## 8. `plan-status` is report-first

Run `/vault-portfolio:portfolio plan-status`. The command runs the audit without `--fix` and
the model presents the classes. Through the command, `--fix` prints `no tty — skipped` per
candidate and changes nothing. In a terminal, with `--fix`, each candidate needs its own `y`;
answer `n` to all and check that no plan changed. Answer `y` to one, then run
`--restore <run-id>` and check that the plan is back byte for byte.

## 9. Only the fixed read-only lines run without a prompt

- Run `/vault-portfolio:portfolio` with nothing else. The three dry runs (`portfolio-scan.py`,
  `portfolio-unify.py`, `portfolio-rebuild.py`, each with no arguments) run with no permission
  prompt, and nothing under `$T` changes.
- Run `/vault-portfolio:portfolio maturity`. `_config.py` and `records-home.py --all-homes`
  run with no prompt, and the model takes each home from the `--all-homes` JSON. Set
  `records: repo` on `apps/example-cli`: it is listed as skipped, with its reason.
- Run `/vault-portfolio:portfolio rebuild --write`. Claude Code asks permission first; decline,
  and nothing is written.
- Run `/vault-portfolio:portfolio scan --root '$T/dev'` and
  `/vault-portfolio:portfolio scan --root x;id`. The model names the refused character and runs
  nothing.

Lesson: a grant ending in `*` pre-approves every flag, write flags included, for the whole turn
while the skill reads vault text. Only exact lines are granted, so the permission prompt is the
confirmation for every other line.

## Runs

<append one dated line per run: what was run, pass or fail, deviations>
