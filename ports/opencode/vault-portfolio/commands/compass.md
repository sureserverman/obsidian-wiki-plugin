---
disable-model-invocation: true
description: Scan every portfolio project's work state, then hand the JSON to the compass skill
argument-hint: "[now|next|review]"
allowed-tools: Read, Glob, Grep, Bash(python3 <vault-portfolio-plugin>/skills/vault-compass/scripts/compass-scan.py)
---

> **On OpenCode this file is not a command.** OpenCode's commands are `/vault-portfolio`
> and `/vault-compass` (`commands/vault-portfolio.md` and `commands/vault-compass.md`),
> which load the skill. The skill reads this file for the rules its own script lines
> follow. The front matter, `$ARGUMENTS` and the permission wording are Claude Code's: on
> OpenCode, `$ARGUMENTS` is the text after the command, or what the user asked of the
> skill, and OpenCode's `permission` settings decide whether a line asks the user first.

**Run the scanner here, in the command, then use the `compass` skill on its output.**
All of compass's evidence comes from one run of one script:

```bash
python3 <vault-portfolio-plugin>/skills/vault-compass/scripts/compass-scan.py
```

Run it exactly so: no flags, no `cd`, no pipe, no redirection. The grant above is that exact
line, with no wildcard, so it allows that line and nothing else; any other command goes
through Claude Code's normal permission prompt. Keep the scanner's stdout, its stderr and its
exit status as printed, then use the `compass` skill with them and the mode.

The grant stays in force for the whole turn, including while the skill runs and reads
text that came out of the vault. That is why it names one fixed line.

**Arguments**: `$ARGUMENTS` is the mode: `now` (what is in flight), `next` (what to work
on next) or `review` (what needs attention). Empty means `now`. Anything else: name the
three modes and stop, without running the scanner.

The scanner writes nothing under the vault, `~/.claude/` or any repo. One part of it is not
this plugin's code: when `business_scan` in `~/.config/obsidian-wiki/config.json` (or
`$BUSINESS_SCAN_PATH`) names an external business scanner, `compass-scan.py` runs that
scanner too, and what it does is up to it.

**Examples**:
- `/vault-compass` — the in-flight board
- `/vault-compass next` — ranked recommendations
- `/vault-compass review` — the cadence sweep and a short agenda
