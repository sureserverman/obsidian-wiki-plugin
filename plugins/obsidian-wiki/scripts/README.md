# obsidian-wiki — deterministic lane

This `scripts/` directory is obsidian-wiki's **deterministic lane**, vendored from
a shared determinism kit. It encodes one rule:

> **Mechanical, decidable checks belong in scripts. Semantic judgment belongs to
> the LLM.** Scripts flag; the model decides and writes.

## Layout

```
scripts/
├── lib/findings.sh      # shared finding accumulator + JSON contract (vendored; do not fork)
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
  index remove delete`). This is the single source of truth for the log format the `/log`,
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
> a plugin validator's job — run one, such as `validate-plugin.sh` against this repo.
> The validators here check obsidian-wiki's own domain.

## Local wiki-access pilot (manual, opt-in)

Python 3.12+ with linked SQLite FTS5 and a supported local Linux filesystem is
required. `wiki-access.py` accepts one JSON object on stdin and returns one JSON
object on stdout, without a framing newline. It exposes only `search`, `resolve`,
`get`, `verify_citations` and `status`. `wiki-access-admin.py` accepts only
`refresh` and `check`. Neither entry point accepts source/config/state path
arguments or executes query text as shell code. Public failures contain codes,
never paths, queries, excluded filenames or tracebacks. No query/answer log exists.

The operator creates a 0600 owner-controlled private file at
`${XDG_CONFIG_HOME:-$HOME/.config}/obsidian-wiki/wiki-access.json`:

```json
{"schema":"wiki-access-config.v1","enabled":true,"categories":["Runbooks"],"portfolio":[]}
```

Choose the explicit published-category allowlist for the intended vault.
`portfolio` lists individually approved `Portfolio/<area>/<project>/integration.md`
locators. Missing config or `enabled:false` returns `disabled`; unsafe files or
unsupported configuration refuse. CLI opt-in does not authorize model egress.
The existing `resolve-vault.sh` supplies source selection: `OBSIDIAN_VAULT_PATH`,
the existing `~/.config/obsidian-wiki/config.json` default, then `~/dev/knowledge`.
The published vault-path sidecar remains the existing skills' route; the CLI
resolves current configuration and does not trust a stale sidecar.

Derived state lives under
`${XDG_STATE_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}}/obsidian-wiki/state/wiki-access/<vault-key>/`.
The key binds canonical source-root identity and policy version. State must be
local, outside the source, with 0700 directories and 0600 single-link regular
files. The index, manifest and private receipt-key never enter stdout. Refresh
creates signing state; retrieval cannot create or rotate it. Explicit refresh
publishes an immutable source-checked generation atomically. Interrupted work
never becomes active. Total state is capped at 128 MiB, retaining the active
generation, staging work and transient reader pins; only validated unpinned
derived generations are reclaimed. Source notes and old research archives are
never reclaimed by this tool.

Filesystem locality is enforced for derived state. Configuration files are
checked for ownership, private mode, regular-file identity and absence of links;
their filesystem type is not separately restricted. Successful responses also
recheck configuration and source selection before disclosure.

Examples from the installed plugin's `scripts/` directory:

```bash
./wiki-access-admin.py <<'JSON'
{"schema":"wiki-access.v1","operation":"refresh"}
JSON
./wiki-access.py <<'JSON'
{"schema":"wiki-access.v1","operation":"resolve","selector":{"kind":"path","value":"Runbooks/Amber.md"}}
JSON
./wiki-access.py <<'JSON'
{"schema":"wiki-access.v1","operation":"search","query":"amberctl --check","limit":5}
JSON
./wiki-access-admin.py <<'JSON'
{"schema":"wiki-access.v1","operation":"check"}
JSON
```

Use returned generation/page IDs in a `get` request. One to five notes are read
as complete safe projections. Its `byte_budget` defaults to 24,000 and includes
all serialized metadata, maps and the signed receipt. Oversized notes are omitted
with `over_budget`; an all-omitted bundle has no receipt. Clients must track a
cumulative 24,000-byte evidence-response budget per answer across repeated calls.
Discovery excerpts cannot serve as full-note evidence.

`verify_citations` takes the returned `read_receipt` and a list of every citation
occurrence, each with `target`, `page_id`, UTF-8 byte `start`/`end`, and exact
`quote`. Targets are exact root-relative published locators including `.md`,
optionally followed by an existing `#Heading` or `#^block-id`. The declared
subset supports ATX headings outside code/comments and existing alphanumeric/hyphen
inline block IDs on plain paragraphs and individual list items. Separate-line IDs
on structured blocks, quoted/fenced/indented code, comments and uncertain HTML/math
contexts refuse; use a page citation with the exact read span instead.
Duplicate or unsupported headings downgrade to page citations or
refuse; unknown anchors refuse. Read/source byte maps accompany valid spans.
Each occurrence labels `target_verified` and `read_verified`; `verified_at` is a
UTC Unix timestamp in seconds. Results explicitly say `structural_only`; claim support, dates, modality and
contradictions still require separate judgment. Receipts expire after 900 seconds
and always require current-source/generation checks.

For stale generations run an explicit admin refresh, then resolve/read again.
Unavailable/corrupt/unsafe stores refuse; there is no stale or direct-source
fallback. To invalidate all receipts, after a first successful refresh run
`wiki-access-admin.py --rotate-receipt-key` with a `refresh` request. This admin
flag never appears on the read entry point. Refresh after source changes also
revokes old-generation receipts. NFS checks describe this host's observed bytes,
not an instantaneous distributed snapshot or revocation of bytes already sent.

Exit codes: 0 successful protocol response (inspect each citation's `valid`),
2 invalid request/schema/filter, 3 exhausted byte/storage budget, 4 operational
unavailability/staleness/permission/disabled, 5 invalid receipt. Both request
boundaries cap stdin at 65,536 bytes; discovery/verification responses cap at
8,000 bytes. Normal ask adoption and packaged-client support are pending their
separate Stage 4 qualification.
