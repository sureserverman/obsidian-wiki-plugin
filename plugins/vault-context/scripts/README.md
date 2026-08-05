# vault-context — deterministic lane

This `scripts/` directory is vault-context's **deterministic lane**, vendored from
the plugin-dev determinism kit. It encodes one rule:

> **Mechanical, decidable checks belong in scripts. Semantic judgment belongs to
> the LLM.** Scripts flag; the model decides and writes.

## Layout

```
scripts/
├── lib/findings.sh      # shared finding accumulator + JSON contract (from plugin-dev; do not fork)
├── lib/eligibility.sh   # the "is this directory a project?" rule — one definition, two callers
├── validate.sh          # orchestrator — discovers and runs every validate-*.sh, merges, prints a verdict
└── validate-link.sh     # a project's vault-context link state: sidecar, CLAUDE.md import, drift, freshness
```

`lib/eligibility.sh` is shared by the write path and the detect path deliberately.
`write-context.sh` refuses an area directory *before* creating anything (exit 4);
`validate-link.sh` reports the same condition as `link-area-directory` for a sidecar
that predates the guard. One rule, one file — a second copy would drift, and the two
verdicts must agree. Point `VAULT_CONTEXT_REGISTRY` at a fixture to test it.

## What the validator inspects

The domain artifact here is **a target project's link state**, not the plugin — so
`validate-link.sh` takes a *project root* as its root and only activates when that
project has link state (a `.claude/vault-context.md` sidecar or a CLAUDE.md
`vault-context` block):

- `link-circular` (error) — the project sits at or under the resolved vault (the
  deterministic backstop for the `/link` skill's circular-link refusal).
- `link-area-directory` (error) — the root is a grouping folder, not a project: not a
  git repo, and either absent from `~/.claude/projects-registry.yaml` or holding other
  registered projects beneath it.
- `link-sidecar-no-body-markers` / `link-sidecar-no-header` (warn) — the sidecar is
  malformed against `assets/vault-context-template.md`.
- `link-import-missing` / `link-import-dangling` / `link-import-no-ref` (warn) — the
  sidecar and the CLAUDE.md `@.claude/vault-context.md` import block disagree.
- `link-sidecar-stale` / `link-index-stale` (info) — freshness nudges.

The "activate only when the artifact is present" guard lets `validate.sh
<plugin-root>` (the structural gate) pass trivially green while `validate.sh
<project-root>` does the real runtime work — one code path, no false findings.

Run the whole lane:

```bash
bash scripts/validate.sh <project-or-plugin-root> [--json]
```

`--json` emits the contract (consumed by `/vault-context:status` and the `link`
skill's post-write verification); without it, a human report.

## What stays judgment (not here)

Which vault pages actually matter to a project (the `match-index.py` scoring is
deterministic, but presenting it isn't), the user-facing status wording, the decision
to refresh or unlink, and the `NO_MATCHES` fallback text. Those live in the
commands/skill, which run this script and consume its JSON.

## The JSON contract

Every `validate-*.sh`, with `--json`, prints:

```json
{"validator","target","summary":{"errors","warnings","info"},
 "findings":[{"severity":"error|warn|info","rule","category","path","line","message"}],
 "verdict":"pass|pass-with-warnings|fail"}
```

Exit code: `1` if any error, else `0` (`2` usage, `3` jq missing).

## Adding a domain validator

Each `validate-<domain>.sh` checks one slice of vault-context's domain — only things
decidable by a rule (parse, field presence, enum, count, regex). Source the lib,
guard `jq`, call `add_finding <severity> <rule-id> <category> <path> <line> <msg>`
per check, end with `render_findings`. Anything requiring taste or rewriting is
**not** a script — it stays with vault-context's skills/agents, which run `validate.sh`
and consume its JSON instead of re-deriving the rules.

> Validating vault-context's *plugin structure* (manifest, frontmatter, layout) is
> plugin-dev's job — run plugin-dev's `validate-plugin.sh` against this repo.
> The validators here check vault-context's own domain.
