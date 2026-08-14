---
description: Scan the current project, match against the vault index, and write a vault-context sidecar
allowed-tools: Bash(bash:*), Bash(python3:*), Read, Write, Edit, Glob, Grep
---

**Run the deterministic pipeline here, in the command, then invoke the skill.**
Every mechanical step is a plugin script; none of it belongs in the model:

```bash
VAULT="$(bash "$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh")"
bash "$CLAUDE_PLUGIN_ROOT/scripts/extract-project-signals.sh" \
  | python3 "$CLAUDE_PLUGIN_ROOT/scripts/match-index.py" "$VAULT/index.md"
bash "$CLAUDE_PLUGIN_ROOT/scripts/write-context.sh" "<project name>" "$VAULT"
bash "$CLAUDE_PLUGIN_ROOT/scripts/validate-link.sh"
```

`write-context.sh` enforces the area-directory guard itself (DEC-001: containment
decides what a project is), so a refusal here is authoritative — do not work around it.

Then use the `link` skill to add the `CLAUDE.md` import block, interpret the
validator output and report.

The shell grant lives at this layer deliberately. This command writes into whatever
project directory the session happens to be in — the surface the 2026-08-13 audit
rated HIGH — and a command runs only when the user types it, whereas a skill can be
triggered by natural language influenced by an ingested source. Also adds a delimited `@.claude/vault-context.md` import block to project
`CLAUDE.md` so future Claude Code sessions load the briefing automatically.

**Arguments**: `$ARGUMENTS` — pass `--force` to overwrite an existing sidecar without
asking. Default behavior errors out if `.claude/vault-context.md` already exists, to
prevent silent overwrites. Use `/vault-context:refresh` for the normal "re-scan" flow.

**Preconditions**: a vault must be configured (env var, config file, or fallback) and
`<vault>/index.md` must exist. If the index is missing, run `/obsidian-wiki:index` from
the vault first.

The current directory must also be a **project** — a git repo, or a `path:` in
`~/.claude/projects-registry.yaml` with no other registered project beneath it. An
*area directory* (a grouping folder such as `~/dev/ai-tools`, whose children are the
projects) is refused with an explanatory message and nothing is written; link the
child projects instead.

This command **only writes** inside the project: `<project>/.claude/vault-context.md`
and a delimited block in `<project>/CLAUDE.md`. The vault is never modified.

**Examples**:
- `/vault-context:link` — first-time link for this project
- `/vault-context:link --force` — overwrite an existing sidecar
