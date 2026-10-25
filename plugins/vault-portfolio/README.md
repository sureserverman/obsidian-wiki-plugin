# vault-portfolio

The cross-project layer for the `planning` plugin. It keeps each project's plans,
backlog, decisions and maturity checklist in an Obsidian vault, under
`<vault>/Portfolio/<area>/<name>/`, and rolls them up into portfolio dashboards.

It plugs into planning through one call: planning's records resolver. Point
planning's config at this plugin's `scripts/records-home.py` and planning's
records land in the vault instead of the repo's `docs/`.

Two commands ship here, each with a skill of the same name:
`/vault-portfolio:portfolio` (scan, unify, maturity, migrate, integrate, rebuild,
plan-status, decisions) and `/vault-portfolio:compass` (now, next, review). The
commands run the scripts and hand the output to the skills, which hold no shell grant
of their own. A command's grants are exact,
read-only command lines with no wildcard, and they stay in force for the whole turn,
skill included. Every other line, each write flag included, goes through Claude Code's
permission prompt, and a write happens only when the user types its flag on the
command. Every write mode refuses while another owner holds the vault's maintenance
window. The vault comes from obsidian-wiki's own config, and nothing is written to a
vault that is not configured.

This file is the plugin's own README. Setup, the config line for planning, the vault
and registry order and the resolver's exit codes are in the marketplace's
`docs/vault-portfolio.md`.
