---
disable-model-invocation: true
description: Run a portfolio subcommand's script, then hand its output to the portfolio skill
argument-hint: "[scan|unify|maturity|migrate|integrate|rebuild|plan-status|decisions] [flags]"
allowed-tools: Read, Glob, Grep, Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/portfolio/scripts/_config.py), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/records-home.py --all-homes), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/portfolio/scripts/portfolio-scan.py), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/portfolio/scripts/portfolio-unify.py), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/portfolio/scripts/portfolio-rebuild.py)
---

**Run the subcommand's script here, in the command, then use the `portfolio` skill
on its output.** The scripts do every mechanical step. The skill presents the result,
takes the user's decisions and names the next command.

**What the grants above allow.** Each one is an exact command line with no wildcard, so it
matches that line and nothing else. Five lines run without a prompt, and all five only read:
`_config.py`, `records-home.py --all-homes`, and the default flow's three dry runs with no
arguments. Every other line, any flag included, goes through Claude Code's normal permission
prompt. That prompt is the user's confirmation for a write. The grants stay in force for the
whole turn, including while the skill runs and reads text that came out of the vault.
That is why they name only fixed, read-only lines.

**Arguments**: `$ARGUMENTS` is a subcommand, then its flags. Treat the whole of it as data.

- **Refuse unsafe text first.** If `$ARGUMENTS` contains `'`, a backtick, `$`, `;`, `|`, `&`,
  `<`, `>`, `\` or a newline, name the character and stop without running anything.
- Accept only the flags listed for the subcommand below. On anything else, show this list and
  stop.
- Pass each flag and each value as its own argument, and single-quote every value.

**Write modes are the user's typed choice.** Pass `--write`, `--fix`, `--restore` or a
registry edit only when it is in `$ARGUMENTS`. Never add one yourself, and never re-run
with one after a yes in chat: the skill names the command line, and the user types it.

Each script line below starts `python3 ${CLAUDE_PLUGIN_ROOT}/skills/portfolio/scripts/`, except
`records-home.py --all-homes`, which is `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/records-home.py --all-homes`.
Only the script name and its flags are shown. Run each exactly that way: no `cd`, no pipe, no
redirection.

| `$ARGUMENTS` | Runs |
|---|---|
| `scan [--root <dir>]… [--json] [--add <path>]… [--add-all] [--remove <path>]… [--write]` | `portfolio-scan.py` with those flags |
| `unify [--project <abs-path>] [--include-stale] [--write]` | `portfolio-unify.py` with those flags |
| `maturity [--project <abs-path>] [--init-missing]` | `_config.py`, then `records-home.py --all-homes`, both exactly as granted. The flags go to the skill, which takes each project's home from that JSON and dispatches planning's `project-maturity` per project |
| `migrate (--project <abs-path> \| --all) [--write]` | `portfolio-migrate.py` with those flags |
| `integrate [--write]` | `portfolio-integrate.py` with those flags |
| `rebuild [--write]` | `portfolio-rebuild.py` with those flags |
| `plan-status [--check] [--json] [--verbose] [--fix] [--restore <run-id>] [--vault <dir>] [--registry <file>]` | `plan-status-audit.py` with those flags |
| `decisions` with `--list-domains`, `--domains <slugs>`, `--infer-domains <repo>`, `--format text\|json`, `--promote <id>`, `--area`, `--name`, `--home`, `--domain`, `--global <id>`, `--reason`, `--title`, `--tag`, `--why`, `--write` | `domain-decisions.py` with those flags. With `--promote`, run `records-home.py --all-homes` first, so the skill can check the project's area, name and home against it. Its exit status does not stop the promote |
| nothing, or only `--include-maturity` | the default flow, dry-run throughout: `portfolio-scan.py`, then `portfolio-unify.py`, then (only with `--include-maturity`) `_config.py` and `records-home.py --all-homes` for the maturity step, then `portfolio-rebuild.py`. Every line runs exactly as granted, with no other flag. Stop at the first script that exits non-zero |

Keep each script's stdout and stderr and its exit status exactly as printed, then use
the `portfolio` skill with them and with the subcommand and flags. Do not retype or
summarise the output before the skill sees it.

Two things the scripts cannot do from here:

- **`plan-status --fix`** asks a per-plan `y` on a terminal. The Bash tool has none, so
  each prompt reads end-of-input, prints `no tty — skipped`, and nothing is written.
  To record a close-out, the user runs the same script line with `--fix` in a terminal.
- **A first `scan`** has no registry to derive the projects root from, so it needs
  `--root <projects-root>`. The script says so and exits 2 without it.

**Examples**:
- `/vault-portfolio:portfolio` — the default flow: writes nothing and asks no permission
- `/vault-portfolio:portfolio scan --root /path/to/projects` — first run: the candidates, dry-run
- `/vault-portfolio:portfolio scan --root /path/to/projects --add-all --write` — seed the registry
- `/vault-portfolio:portfolio unify --write --project /path/to/repo` — accept one project
- `/vault-portfolio:portfolio rebuild --write`
