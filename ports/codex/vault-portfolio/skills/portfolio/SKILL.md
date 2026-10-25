---
name: portfolio
allowed-tools: Read, Glob, Grep
description: "Portfolio records in the vault: scan, unify, maturity, migrate, integrate, rebuild, plan-status and decisions."
---

> **On Codex, this skill runs its own script lines.** Codex has no plugin commands, so
> nothing runs a script and hands you its output. Wherever this skill or a reference says
> the command runs a line, run that line yourself, by the rules in
> `<vault-portfolio-plugin>/commands/portfolio.md`: refuse the unsafe characters it names,
> accept only the flags its table lists for the subcommand, pass each flag and each value
> as its own argument with every value single-quoted, and run each line exactly as shown,
> with no `cd`, pipe or redirection. Keep each script's stdout, stderr and exit status as
> printed. `<vault-portfolio-plugin>` is this plugin's folder, two levels above the folder
> this file is in. Read "never run the script yourself" below as: never run a line the
> command would not run. The command's grants are Claude Code's: on Codex, its approval
> policy decides which lines ask the user first. A write happens only when the user typed
> its flag (`--write`, `--fix`, `--restore` or a registry edit) after
> `$vault-portfolio:portfolio`: never add one yourself, and after a yes in chat, name the
> exact command line for the user to type rather than running it.

# Portfolio Orchestrator

One skill that ties together every project the registry lists:

1. A **registry** of tracked projects. Schema in `references/registry-format.md`.
2. **Per-project backlog candidates** from plans, via `scripts/portfolio-unify.py`, which reads plans through the vendored plan parser.
3. **Per-project maturity** audits and a roll-up, via planning's `project-maturity` skill.
4. **Inter-project edges**, their symmetry, and cross-project arcs. Formats in `references/integration-format.md` and `references/integration-plan-format.md`.
5. **Architectural decisions**, per project and per architecture domain, rolled up to `global-decisions.md`. Format in `references/decisions-format.md`. The per-domain half is this skill's `decisions` subcommand; the per-project half is authored by planning's `decisions` skill.

**The vault holds the records.** Each project's plans, backlog, maturity checklist, decisions and integration edges live under `<vault>/Portfolio/<area>/<name>/`. The roll-ups live in `<vault>/Portfolio/`: `global-backlog.md`, `global-maturity.md`, `global-decisions.md`, `global-security.md`, `global-business.md` (only with a business scanner), `integration-graph.md` and `integration-backlog.md`. Templates in `references/global-formats.md`.

## Where things resolve (read this before any read or write)

```
repo <projects-root>/<area>/<project>  →  <vault>/Portfolio/<area>/<name>/
```

- **The vault** is `$OBSIDIAN_VAULT_PATH`, else `default_vault` in `~/.config/obsidian-wiki/config.json`, else the legacy `vault_dir` in `~/.claude/portfolio-config.yaml`. **The registry** is the `registry` key in that `config.json`, else `~/.claude/projects-registry.yaml` when it exists, else `~/.config/obsidian-wiki/projects-registry.yaml`. `scripts/_config.py` prints both as JSON, with `business_scan`, and exits 2 on a config file that does not parse; the command runs it for `maturity`.
- **A project's home** comes from `records-home.py --all-homes`, which the command runs for `maturity` and before a `decisions --promote`. Its JSON lists every registry project with `name`, `area`, `path`, `enabled`, `home` (absolute, or `null`), `records` (`vault` or `repo`) and `reason` (why `home` is `null`). Take each home from that JSON; never derive one in prose, and never run the script yourself. A project with `records: repo` has no vault home. The resolver's contract (exit codes, `--for-write`, the opt-out) is in `references/registry-format.md`.
- **No silent fallback.** With no vault set, every subcommand that resolves a home **fails loudly**: the subcommand scripts print `portfolio not configured: …` and stop, and `records-home.py` exits 3 ("not managed here"). They never fall back to `~/dev/knowledge` (obsidian-wiki's own default) or to the repo's `docs/`. Planning's own fallback to `<repo>/docs` is planning's rule, not this skill's.
- **A missing vault is not an empty vault, and an unmounted one is not missing.** A vault that is *set* but unreachable is refused the same way (`vault unreachable: …`), and no part of the tree is created. Unreachable means relative, absent, unreadable, or **existing with no `Portfolio/`**, which is what an unmounted mountpoint looks like. The `Portfolio/` check is what stops `migrate` from building a phantom vault at a mount point and moving a repo's only docs into it. Initialise a new vault by creating `<vault>/Portfolio/` once, by hand. Read-only tools refuse too, because an empty result reads as "nothing is in flight". `vault_problem()` in `scripts/portfolio-rebuild.py` is the one definition every script uses.
- **A foreign maintenance window refuses every write.** Every write mode (`--write`, `--fix`, `--restore`) calls obsidian-wiki's `require_write_access()` before its first write, and exits non-zero while another owner holds the vault's maintenance window.

**Announce at start:** "Using the portfolio skill — `<scan|unify|maturity|migrate|integrate|rebuild|plan-status|decisions|default>`."

---

## Reference map

The trunk carries what binds every run. These load when their condition is met. Read the one you need rather than working from memory.

| Read this | When |
|---|---|
| `references/subcommand-scan.md` | running `scan`: first-run seeding, drift detection |
| `references/subcommand-unify.md` | running `unify`: the sweep and its report |
| `references/subcommand-maturity.md` | running `maturity`, or why the default flow gates it |
| `references/subcommand-migrate.md` | running `migrate`: steps, preflight skips, rollback |
| `references/subcommand-integrate.md` | running `integrate` |
| `references/subcommand-rebuild.md` | running `rebuild`: the steps and both optional layers |
| `references/subcommand-plan-status.md` | running `plan-status`: classes, evidence grades |
| `references/subcommand-decisions.md` | running `decisions`: domain registers, digest, inference, promotion |
| `references/registry-format.md` | the registry schema, or resolving a repo's home |
| `references/domain-slugs.md` | mapping a repo's stack to domain registers |
| `references/global-formats.md` | reading or writing `global-backlog.md` / `global-maturity.md` |
| `references/decisions-format.md` | reading or writing a decisions register, or `global-decisions.md` |
| `references/global-security-format.md` | reading `global-security.md` or its input |
| `references/sidecar-format.md` | a repo's `vault-context.md` block |
| `references/integration-format.md` | reading or writing a project's `integration.md` |
| `references/integration-plan-format.md` | an integration arc under `Portfolio/integrations/` |
| `references/integration.md` | routing an ask to a neighbouring skill |
| `references/extraction-classification.md` | changing what this trunk keeps and what moves to a reference |

---

## Subcommands

An explicit invocation runs exactly one. The default flow composes four, one of them gated (§ Staged rollout). Each procedure lives in its own reference.

### `scan` — load the registry, detect drift, optionally first-run-seed

The command runs `scripts/portfolio-scan.py`, which walks `<projects-root>/` and reports drift (found but not registered, registered but missing) on every run. A first run, with no registry yet, needs `--root <projects-root>`; it seeds the registry and then **exits** (the user re-invokes for the actual work). The registry changes only when the user types `--write` with `--add`, `--add-all` or `--remove`. Procedure: `references/subcommand-scan.md`.

### `unify` — derive backlog candidates for every enabled project

The command runs `scripts/portfolio-unify.py` over the whole registry in one process. Its report is presented for accept-all, accept per project, or skip; an accepted set is written when the user types `unify --write` (with `--project` per accepted project). **Never write during dry-run.** No fan-out: the parse is decidable, so the model's part is the confirm. Procedure: `references/subcommand-unify.md`.

### `maturity` — audit per-project MATURITY.md and surface staleness

The command runs `scripts/_config.py` and `records-home.py --all-homes`; this skill takes the projects and their homes from that JSON and fans out planning's `project-maturity audit --write` per project (same 8-in-flight cap), then reports stale manual claims (>90 days) and `[?] stale-detector` markers, which block ship-ready. **A project with no MATURITY.md is skipped, not scaffolded**, unless `--init-missing` is passed. Procedure: `references/subcommand-maturity.md`.

### `migrate` — move a project's operational docs from its repo into the vault (one-time)

The command runs `scripts/portfolio-migrate.py`. It moves `<repo>/docs/plans/**`, `docs/backlog.md` and `docs/MATURITY.md` into the project's vault home. **All-or-nothing, and the order is copy → verify → delete:** it copies every file, checks `sha256(source) == sha256(destination)` for each, and only then removes the repo sources. An interruption therefore leaves the repo intact, and any mismatch aborts that project, deletes the partial vault copies and leaves the repo untouched. Never `git mv`, never a bare `mv`; dry-run unless `--write`. A vault home that already holds `plans/`, `backlog.md` or `MATURITY.md` is SKIPPED for manual resolution, **never overwritten or merged**. Procedure, the other preflight skips and rollback: `references/subcommand-migrate.md`.

### `integrate` — roll up inter-project edges and the integration backlog

The command runs `scripts/portfolio-integrate.py`, which rolls every project's `integration.md` into `Portfolio/integration-graph.md` and `Portfolio/integration-backlog.md`. **Symmetry rule:** if A declares `impacts: [[B]]`, B must declare `depends_on: [[A]]`, and the other way round. Asymmetries are **reported, never auto-fixed**; the user resolves them by editing one side. Dry-run by default; `--write` persists. Procedure: `references/subcommand-integrate.md`.

### `rebuild` — regenerate the global roll-ups and the sidecar blocks

The command runs `scripts/portfolio-rebuild.py`. It regenerates `global-backlog.md`, `global-decisions.md`, `global-maturity.md`, the security dashboard and, when a scanner is configured, the business dashboard, and refreshes every enabled project's `PORTFOLIO-STATUS` sidecar block. It refuses when the vault is unset or unreachable. Three rules bind it whatever else changes:
- the hand-curated `<!-- BEGIN PRESERVE -->` block survives **byte-for-byte**, and an ambiguous one is refused rather than rewritten;
- a missing or failed business or security layer degrades to one status line and **never truncates an existing roll-up**;
- an unrecorded security count renders `?` and **never `0`**: unmeasured is not clean.

Procedure: `references/subcommand-rebuild.md`.

### `plan-status` — reconcile every vault plan's recorded status against its real progress

The command runs `scripts/plan-status-audit.py` over every plan in the vault. **Report-first: the default invocation writes nothing.** `--fix` presents one candidate at a time with its graded evidence and requires a per-plan `y` on a terminal, so through the command it writes nothing (`no tty — skipped`); the user runs it in a terminal to record. It takes a backup under the plan's directory, in `.audit-backups/<run-id>/`, first; `--restore <run-id>` is the only undo the vault has. A plan carrying a bracketed `Status:` marker outside `[ xX~]` is **never offered as a completion candidate, under any flag**, and the audit **never infers `**Abandoned:**`**. Classification order and evidence grades: `references/subcommand-plan-status.md`.

### `decisions` — the per-domain half of the decisions register

The command runs `scripts/domain-decisions.py`: list the domain registers, digest the ones a project's stack points at, infer those slugs from a repo's files, and promote a project decision into a domain register. Superseded entries come back **marked, not filtered**, and malformed blocks **flagged, not dropped**. `--promote` prints its edits and writes only with `--write`, and **writes both link directions or neither**. Procedure: `references/subcommand-decisions.md`.

### Default flow (no subcommand, or explicit `portfolio` invocation)

Composes four ops in order: `scan` → `unify` → `maturity` (only with `--include-maturity`, see § Staged rollout) → `rebuild`. The command runs every script dry, so the default flow writes nothing; present each report and name the `--write` command lines the user can type next. Exits when done; the user re-invokes single subcommands to drill in.

**Idempotency guarantee:** if nothing changed upstream (no new plans, no plan edits, no claim refreshes), a second consecutive `portfolio` run writes nothing. The registry, per-project backlogs, MATURITY files, sidecars and roll-ups are left as they were. The roll-ups compare their content without the `**Last rebuilt:**` line, so a date change alone writes nothing.

---

## Staged rollout

The default `portfolio` flow leaves maturity out:

- `portfolio maturity` (explicit subcommand invocation) works normally.
- `portfolio` (default flow) skips the maturity step UNLESS `--include-maturity` is passed.

Why the gate exists: `references/subcommand-maturity.md`.

---

## Configuration

The vault and registry settings live in obsidian-wiki's config, `~/.config/obsidian-wiki/config.json`. Every key is optional:

```json
{
  "default_vault": "~/vault",
  "registry": "~/.config/obsidian-wiki/projects-registry.yaml",
  "business_scan": ["python3", "~/tools/business/business-scan.py"]
}
```

- `default_vault` is the vault. `$OBSIDIAN_VAULT_PATH` outranks it, and the legacy `vault_dir` in `~/.claude/portfolio-config.yaml` is read when neither is set. With none of the three, the vault is **unset**, which is a hard refusal under § Where things resolve, never a fallback. A config file that is present but does not parse, or a key of the wrong type, is refused too.
- `registry` names the registry file. Without it, the order in § Where things resolve applies.
- `business_scan` is an argv list naming **an optional external scanner** (each item starting with `~` is expanded). `$BUSINESS_SCAN_PATH`, a script run with the same Python, outranks it. With neither, the business layer is off and nothing else changes. Its contract: `references/subcommand-rebuild.md`.

A vault that is *set* but unreachable gets **the same refusal** as an unset one. It is not the lesser failure: unset has no destination to get wrong, while a stale or unmounted path is one `mkdir -p` away from a plausible second vault.

## File conflicts and write discipline

This skill controls three write surfaces directly through its scripts: the registry (only through `scan --write`, typed by the user; planning's `records-home.py --for-write` call is the one other writer), the roll-ups in `<vault>/Portfolio/`, and the `PORTFOLIO-STATUS` block in each repo's sidecar. It controls two indirectly, through planning's skills: each project's `backlog.md` (`backlog add`) and `MATURITY.md` (`project-maturity audit --write`).

Hard rules:

- Never mutate a project's backlog or MATURITY.md by hand from this skill. `unify --write` appends to the backlog through its script; everything else goes through `backlog` or `project-maturity`.
- The registry is read-mostly. Append, remove or toggle single entries; never rewrite it whole.
- Parallel sub-agents write to DIFFERENT projects' files; no two agents touch the same path. The registry being a flat list (no project nesting) is what makes that hold.

## Hard rules

- Dry-run is the default for every write-capable subcommand.
- The first-run flow never touches project files. It only writes the registry, and only on the user's typed `scan --write`.
- Drift is reported on every run, even when there is none: the report header is the proof the check happened.
- The 8-in-flight cap on parallel sub-agents is non-negotiable and not configurable from the CLI.
- `enabled: false` projects appear in `scan` output but are excluded from `unify`, `maturity`, `migrate`, `rebuild`, `compass` and `security-scan`.
- `records: repo` projects keep their records in the repo. Every script honours that: no vault home, no sidecar home block, and no `migrate` or `unify` action for them. `maturity` skips them too, naming the `reason` from `--all-homes`. Their edges are the exception: `integrate` reads `<vault>/Portfolio/<area>/<name>/integration.md`, because edges name the owner's other projects and stay in the vault.

## Integration

Routes to planning's `planning-projects` and `executing-plans` (which produce and tick the plans `unify` parses), `backlog` (the register `unify` appends to), `project-maturity` (per project, via sub-agent), `decisions` (the per-project register), `dispatching-parallel-agents` (the `maturity` fan-out), and to `compass` (which reads, never writes, the artifacts this skill maintains). What each is for: `references/integration.md`.

## Remember

- `scan` → `unify` → `maturity` → `rebuild`. The default flow runs all four; subcommands are for drill-in.
- First-run flow seeds the registry and EXITS; no project files touched.
- Dry-run is the default; nothing writes until the user types `--write`.
- Re-running with no upstream changes writes nothing.
- The registry is the canonical project list; the walk runs on every `scan` and every default-flow run to surface drift.
