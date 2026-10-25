# vault-portfolio for OpenCode

The cross-project layer for the `planning` plugin. It keeps each project's plans,
backlog, decisions and maturity checklist in an Obsidian vault, under
`<vault>/Portfolio/<area>/<name>/`, and rolls them up into portfolio dashboards.

Two skills ship here: `vault-portfolio` (scan, unify, maturity, migrate, integrate,
rebuild, plan-status, decisions) and `vault-compass` (now, next, review). Each has a
command of the same name. The vault comes from obsidian-wiki's own config, and nothing
is written to a vault that is not configured.

## Install

```bash
bash ports/opencode/install.sh --dry-run   # the plan and the config entries; writes nothing
bash ports/opencode/install.sh
```

The installer:

- syncs this folder to `<plugins>/vault-portfolio`, removing files a newer port no longer
  ships. `<plugins>` is `$OPENCODE_PLUGIN_LOCAL_ROOT`, else
  `${XDG_DATA_HOME:-~/.local/share}/opencode-plugins`;
- copies `commands/vault-portfolio.md` and `commands/vault-compass.md` into
  `${XDG_CONFIG_HOME:-~/.config}/opencode/commands/`;
- never edits `opencode.json`. It prints the entries below for you to add;
- never writes under `~/.claude` or `~/.agents`. OpenCode also reads skills from those
  folders, so a target there is refused, and so is a target that is a symlink.

Restart OpenCode after adding the entries.

## The opencode.json entries

```json
{
  "skills": { "paths": ["<plugins>/vault-portfolio/skills"] },
  "permission": {
    "external_directory": {
      "<vault>/Portfolio/**": "allow",
      "<plugins>/vault-portfolio/**": "allow"
    }
  }
}
```

Merge them into the file's `skills` and `permission` objects if it already has them. The
installer prints them with your paths filled in. It reads the vault the way the plugin's
scripts do, and keeps `<vault>` as a placeholder when no vault is configured.

- **`skills.paths`** is how OpenCode finds the two skills. A probe measured only a copy in
  `~/.config/opencode/skills` winning over a same-named skill in `~/.claude/skills` or
  `~/.agents/skills`. Whether a `skills.paths` copy wins the same way was not measured.
- **`<vault>/Portfolio/**`** is the records home. Records land there, outside any
  workspace. OpenCode asks before a tool call outside the workspace unless
  `permission.external_directory` allows it.
- **`<plugins>/vault-portfolio/**`** is the plugin's own folder. OpenCode allows each
  skill's folder by itself, but the rules file and the scripts at the plugin's root sit
  outside them.

## Invoke the skills by name

OpenCode does not reliably pick a skill from a plain request. Name it:

- `/vault-portfolio [subcommand] [flags]`, for example `/vault-portfolio rebuild --write`;
- `/vault-compass [now|next|review]`;
- or name the skill in the prompt: "use the vault-portfolio skill to run plan-status".

## Check that the records landed

`opencode run` refuses a tool call outside the workspace without asking, and still exits 0.
The run prints a preamble and no error. So a script or a non-interactive run must never
trust the exit status. After any write mode (`--write`, `--fix`, `--restore`), or a
planning record written into the vault, check that the record exists under
`<vault>/Portfolio/<area>/<name>/`, and fail loudly when it does not.

## How it runs on OpenCode

An OpenCode command is a prompt: `/vault-portfolio` and `/vault-compass` load the skill
and run nothing themselves. Each skill runs its own script lines. `commands/portfolio.md`
and `commands/compass.md` are the rules those lines follow (the flags each subcommand
accepts and the characters refused), not commands OpenCode runs. OpenCode's `permission`
settings decide whether a line asks you first. A write happens only when you type its flag.
Every write mode refuses while another owner holds the vault's maintenance window.

Planning reaches this plugin through its records resolver: point planning's
`records_resolver` setting at `scripts/records-home.py` in the installed plugin folder.
Setup, the vault and registry order and the resolver's exit codes are in the
marketplace's `docs/vault-portfolio.md`.
