# vault-portfolio

The cross-project layer for the `planning` plugin. It keeps each project's plans,
backlog, decisions and maturity checklist in an Obsidian vault, under
`<vault>/Portfolio/<area>/<name>/`, and rolls them up into portfolio dashboards.

It plugs into planning through one call: planning's records resolver. Point
planning's config at this plugin's `scripts/records-home.py` and planning's
records land in the vault instead of the repo's `docs/`.

Two skills ship here: `$vault-portfolio:portfolio` (scan, unify, maturity, migrate,
integrate, rebuild, plan-status, decisions) and `$vault-portfolio:compass` (now, next,
review). Codex has no plugin commands, so each skill runs its own script lines. The
files under `commands/` are the rules those lines follow (the flags each subcommand
accepts and the characters refused), not commands Codex can run. Codex's approval
policy decides whether a line asks the user first, and a write happens only when the
user names its flag. Every write mode refuses while another owner holds the vault's
maintenance window. The vault comes from obsidian-wiki's own config, and nothing is
written to a vault that is not configured.

This file is the plugin's own README. Setup, the config line for planning, the vault
and registry order and the resolver's exit codes are in the marketplace's
`docs/vault-portfolio.md`.
