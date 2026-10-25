# Sidecar Format: Portfolio Status Block (v2)

The portfolio status block is a sentinel-delimited section that `/vault-portfolio:portfolio
rebuild` writes into each enabled registered project's `.claude/vault-context.md`. The
vault-context plugin owns the rest of that file and carries the block across its own
refreshes; this skill owns **only** the content between the sentinels and never touches
anything outside them. Re-runs replace only the block, and everything outside it is preserved
byte-for-byte.

This file is the block contract. vault-context's `write-context.sh` relies on it.

## Sentinels

- **Begin:** `<!-- PORTFOLIO-STATUS-BEGIN — managed by /vault-portfolio:portfolio rebuild; do not hand-edit -->`
- **End:** `<!-- PORTFOLIO-STATUS-END -->`

Insertion logic, in `portfolio-rebuild.py`'s `splice_sidecar()`, which `migrate` uses too:

- If the file holds a begin line starting `<!-- PORTFOLIO-STATUS-BEGIN` and ending `-->`,
  followed later by the end sentinel, and the next rule holds → replace the first such block, from that begin line
  through the end sentinel, with the freshly generated one. The begin line is matched by its
  prefix, not its full wording, because the wording names the owning skill and has changed
  before: a sidecar committed with an older wording gets its block replaced, and the new block
  carries the current begin line.
- Every `<!-- PORTFOLIO-STATUS-BEGIN` in the file must be a whole begin line (its `-->` on the
  same line) with an end sentinel after it and before the next one. Otherwise → leave the file
  unchanged: a begin with no end, a begin without its `-->`, a stray begin ahead of a block,
  or an end before the begin. Guessing where a block starts or ends in a file someone has
  rearranged is how content outside it gets lost, and a block appended after a stray begin
  would let the next run read from that begin to the new end and delete the text between.
- If the file holds no `<!-- PORTFOLIO-STATUS-BEGIN` at all → append the whole block (begin
  sentinel, content, end sentinel) at the end of the file, after exactly one blank line.
- If the file does not exist → create it as `# Vault context for <repo folder name>`, a blank
  line, and the block.

A reader that only needs to *find* the block (vault-context does) matches from
`<!-- PORTFOLIO-STATUS-BEGIN` to `PORTFOLIO-STATUS-END -->` the same way.

`rebuild` skips a file whose bytes are not valid UTF-8 for that run and never overwrites it: everything
outside the sentinels belongs to someone else.

## v2 block template

```
<!-- PORTFOLIO-STATUS-BEGIN — managed by /vault-portfolio:portfolio rebuild; do not hand-edit -->
## Portfolio status

- **Home:** `<home absolute path>`   (plans/backlog/maturity live here, not in this repo's docs/)
- **Plans:** see [plans/](<home>/plans/)
- **Backlog:** see [backlog.md](<home>/backlog.md)
- **Maturity:** see [MATURITY.md](<home>/MATURITY.md)
- **Ship-ready:** see [global dashboard](<vault>/Portfolio/global-maturity.md)
- **Decisions:** see [decisions.md](<home>/decisions.md)   ← only when the file exists
- **⬆ Depends on:** [[X]] (why), [[Y]] (why)        ← only when integration.md declares any
- **⬇ Impacts:** [[B]] (why), [[C]] (why)            ← only when integration.md declares any
- **Inbound integration debt:** see [integration-backlog.md](<vault>/Portfolio/integration-backlog.md)

<!-- PORTFOLIO-STATUS-END -->
```

`migrate` writes a smaller block (the heading and the `Home` line) when it moves a project; the
next `rebuild` replaces it with the full one.

### Pointer-only, not snapshotted

The `Plans`, `Backlog`, `Maturity`, `Ship-ready`, `Decisions` and `Inbound integration debt`
lines are **links, not values**. The sidecar is committed in the repo and therefore lags the
live vault: any count or verdict embedded here (`N open`, a maturity row, `❌ no`, `K items`)
goes stale the moment the vault's files change, and a rebuild only re-syncs it on demand. A
reader who needs the current number opens the linked file. Only the `Depends on` / `Impacts`
wikilinks carry inline content, because edges change rarely and are themselves the payload.

The `Plans` line points at `<home>/plans/` (the directory, not single files), so every plan
saved there is reachable from the sidecar the moment it lands, with nothing to regenerate.

## Field sources

| Field | Source |
|---|---|
| `Home` | `<vault>/Portfolio/<area>/<name>`, from the registry entry's `area` and `name` and the configured vault (`registry-format.md` § The records home). |
| `Plans` | Static link to `<home>/plans/`. |
| `Backlog` | Static link to `<home>/backlog.md`. The open-item count is **not** read or embedded. |
| `Maturity` | Static link to `<home>/MATURITY.md`. No per-axis row is embedded. |
| `Ship-ready` | Static link to `<vault>/Portfolio/global-maturity.md`. No verdict is embedded; the dashboard is authoritative. |
| `Decisions` | Static link to `<home>/decisions.md` (`decisions-format.md`). **Conditional:** emitted only when the file exists, unlike the other pointers. Most projects have no register, and a link to a file that does not exist is worse than no link. |
| `Depends on` | This project's `<home>/integration.md`, `depends_on:` list, read exactly as `integrate` reads it: every entry, a bare `"[[X]]"` string or a mapping, as its wikilink target plus `(why)`, the link alone when there is no `why`. Omitted when there are none. |
| `Impacts` | The same file's `impacts:` list. Omitted when there are none. |
| `Inbound integration debt` | Static link to `<vault>/Portfolio/integration-backlog.md`. No item count is embedded. |

## Why impacts and dependencies are in the sidecar

When a developer opens project A, the session loads `.claude/vault-context.md` at once. The
`⬇ Impacts` line shows there, before any code is read or edited, so the session knows that a
change to A may break B or C. With that in view, the agent (or the developer) can drop an
integration backlog item straight into B's or C's backlog without leaving the session. The
impact shows up at session open, in the project where the change will be made, rather than in a
separate planning run or after the fact.

## Hard rules

- **No tombstone in the repo.** After `migrate`, the sidecar is the only pointer the repo keeps
  to its home. No other pointer file is written into the repo.
- **Idempotent.** Re-running `rebuild` with no upstream change (the registry, the
  integration edges, whether a `decisions.md` exists) produces a byte-identical block, and the file is not rewritten. Field
  values come deterministically from their sources; no timestamps or run ids are embedded.
- **Registry-gated.** Only projects in the registry with `enabled: true` (the default) and
  no `records: repo` receive a block; a `records: repo` project has no vault home to name. A repo that is not in the registry has its `.claude/vault-context.md` left completely
  untouched: the skill does not append to, remove from, or inspect it.
