---
description: Scan the current project, match against the vault index, and write a vault-context sidecar
---

Use the `link` skill to scan the current project, match against
`<vault>/index.md`, and write `<project>/.claude/vault-context.md` with the relevant
vault pages. Also adds a delimited `@.claude/vault-context.md` import block to project
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
