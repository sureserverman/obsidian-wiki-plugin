# obsidian-wiki — deterministic lane

This `scripts/` directory is obsidian-wiki's **deterministic lane**, vendored from
the plugin-dev determinism kit. It encodes one rule:

> **Mechanical, decidable checks belong in scripts. Semantic judgment belongs to
> the LLM.** Scripts flag; the model decides and writes.

## Layout

```
scripts/
├── lib/findings.sh      # shared finding accumulator + JSON contract (from plugin-dev; do not fork)
├── validate.sh          # orchestrator — discovers and runs every validate-*.sh, merges, prints a verdict
├── validate-vault.sh    # vault-page health: broken wikilinks, missing frontmatter, orphans
└── validate-log.sh      # log.md drift: malformed entry headings, unknown entry types
```

## What the validators inspect

The domain artifact here is **the vault**, not the plugin — so the validators take
a *vault path* as their root, and only activate when one is present:

- **`validate-vault.sh <vault>`** — activates when `<vault>/index.md` exists. The
  mechanical half of `/lint`: `vault-broken-wikilink` (a `[[target]]` that resolves
  to no page basename, declared alias, or file — handling `#section`/`|alias`,
  escaped table pipes, fenced code, and path-style links into `raw/`),
  `vault-missing-frontmatter` / `vault-frontmatter-no-title`, and `vault-orphan-page`
  (info). Excludes `raw/`, `.obsidian/`, `.git/`, and the auto-generated `Portfolio/`
  tree, mirroring `build-index.py`.
- **`validate-log.sh <vault>`** — activates when `<vault>/log.md` exists. Asserts the
  `## [YYYY-MM-DD] <type> | <title>` heading contract and that `<type>` is in the
  known set (`ingest query lint schema merge gaps session-import session-capture
  index`). This is the single source of truth for the log format the `/log`,
  `/ingest`, `/merge`, `/lint`, and session skills all write.

The "activate only when the artifact is present" guard is deliberate: it lets
`validate.sh <plugin-root>` (the structural gate) pass trivially green while
`validate.sh <vault>` does the real runtime work — one code path, no false findings.

Run the whole lane:

```bash
bash scripts/validate.sh <vault-or-plugin-root> [--json]
```

`--json` emits the contract (consumed by `/lint` and the `lint` skill); without it,
a human report.

## What stays judgment (not here)

Possible contradictions and possibly-stale claims (`/lint`'s heuristic half), survivor
selection in `/merge`, conflict surfacing in `/ingest`, entity importance in `/gaps`
and `/related`, secret redaction in `/import-session`, and all user-facing wording.
Those need taste or rewriting, so they live in the skills — which run these scripts
and consume the JSON rather than re-deriving the rules.

## The JSON contract

Every `validate-*.sh`, with `--json`, prints:

```json
{"validator","target","summary":{"errors","warnings","info"},
 "findings":[{"severity":"error|warn|info","rule","category","path","line","message"}],
 "verdict":"pass|pass-with-warnings|fail"}
```

Exit code: `1` if any error, else `0` (`2` usage, `3` jq missing).

## Adding a domain validator

Each `validate-<domain>.sh` checks one slice of obsidian-wiki's domain — only things
decidable by a rule (parse, field presence, enum, count, regex). Source the lib,
guard `jq`, call `add_finding <severity> <rule-id> <category> <path> <line> <msg>`
per check, end with `render_findings`. Anything requiring taste or rewriting is
**not** a script — it stays with obsidian-wiki's skills/agents, which run `validate.sh`
and consume its JSON instead of re-deriving the rules.

> Validating obsidian-wiki's *plugin structure* (manifest, frontmatter, layout) is
> plugin-dev's job — run plugin-dev's `validate-plugin.sh` against this repo.
> The validators here check obsidian-wiki's own domain.
