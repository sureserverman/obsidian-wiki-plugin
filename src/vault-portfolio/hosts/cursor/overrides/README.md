# vault-portfolio for Cursor

The cross-project layer for the `planning` plugin, built for Cursor. It keeps each project's
plans, backlog, decisions and maturity checklist in an Obsidian vault, under
`<vault>/Portfolio/<area>/<name>/`, and rolls them up into portfolio dashboards.

It plugs into planning through one call: planning's records resolver. Point planning's
`records_resolver` setting at this plugin's `scripts/records-home.py` in the installed folder
(`~/.cursor/plugins/local/vault-portfolio/scripts/records-home.py` in a local install), and
planning's records land in the vault instead of the repo's `docs/`.

## Install

From a checkout of this repository:

```bash
bash ports/cursor/install.sh vault-portfolio            # -> ~/.cursor/plugins/local/vault-portfolio
bash ports/cursor/install.sh vault-portfolio --dry-run  # show what would change
```

The installer syncs the whole folder with `--delete`, refuses a symlinked target, and writes
nothing else: no hooks, no user config. `CURSOR_PLUGIN_LOCAL_ROOT` moves the local root.

## Use

Two skills ship here, each invoked by name:

- `/vault-portfolio` — scan, unify, maturity, migrate, integrate, rebuild, plan-status and
  decisions. The text after the name is the subcommand and its flags, for example
  `/vault-portfolio rebuild --write`.
- `/vault-compass` — `now`, `next` or `review`: what is in flight, what to work on next, and
  a periodic review sweep. Report-only.

The skills carry a `vault-` prefix on Cursor. Cursor also reads skills from other roots, such
as a Claude Code plugin cache, and a bare `portfolio` or `compass` from one of them could be
served in place of this plugin's copy.

This plugin ships no Cursor command, so each skill runs its own script lines, by the rules in
its SKILL.md: the flags each subcommand accepts, the characters it refuses, one exact line per
script. Cursor's own approval for agent shell commands decides whether a line asks first. A
write happens only when the user typed its flag (`--write`, `--fix`, `--restore` or a registry
edit) after the skill's name. Every write mode refuses while another owner holds the vault's
maintenance window. The vault comes from obsidian-wiki's own config, and nothing is written to
a vault that is not configured.

The text the scripts write into the vault keeps Claude Code's command spelling
(`/vault-portfolio:portfolio rebuild`), so one vault can be maintained from both hosts without
each rebuild rewriting it.

Setup, the config line for planning, the vault and registry order and the resolver's exit
codes are in the marketplace's `docs/vault-portfolio.md`.
