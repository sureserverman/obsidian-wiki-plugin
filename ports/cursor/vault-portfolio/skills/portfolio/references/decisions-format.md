# Decisions Format: per-project `decisions.md` + per-domain `Portfolio/decisions/<domain>.md`

The portfolio records **why the architecture is the way it is** in two linked registers:

- **Per-project:** `<vault>/Portfolio/<area>/<project>/decisions.md`, the decisions that bind
  *this* project. Planning's `decisions` skill authors it.
- **Per-domain:** `<vault>/Portfolio/decisions/<domain>.md`, the decisions that bind every
  project built on one architecture or platform (`android`, `ios`, `rust`, `ubuntu`, `macos`,
  `tor`, …; `domain-slugs.md` maps stacks to slugs). This skill's `decisions` subcommand
  (`subcommand-decisions.md`) reads and promotes into it.

The two are cross-linked in both directions, so a decision is reachable from the project that
feels it *and* from the domain that governs it. This mirrors the Depends-on/Blocks discipline
inside a plan and the symmetry rule of `integration.md` (`integration-format.md`): a
relationship declared on one side only cannot be walked, so both sides declare it, and the
tooling reports, never silently repairs, any gap.

Both files are declarations. `portfolio rebuild` reads them and renders
`Portfolio/global-decisions.md`; it never rewrites either register.

## Why a register and not just the architecture doc

An architecture doc (`plans/YYYY-MM-DD-<topic>-architecture.md`) is ADR-style but
**event-shaped**: it captures one architecture exercise, keyed `ARCH-NN`, and is not revisited
once its plan is executed. Decisions accrete *between* those events: a security review lands a
constraint, a platform deprecation forces a library swap, a packaging limit rules out an
approach. Those have no home in a dated plan file, and no way to be seen across projects that
share a platform. The register is that home. The architecture doc stays the place where a
decision is first *made*, and cites into the register when it is.

## Per-project format

`decisions.md` is a flat list of `## DEC-NNN` blocks, newest first, under a short preamble. Ids
are zero-padded to three digits, monotonic per project, and **never reused**, the same
discipline as `BL-NNN` in the backlog: the next id is `max + 1` even when earlier entries were
superseded.

A register may instead key its entries `DEC-<TAG>-NNN`, where `<TAG>` is a 2–4 letter uppercase
project tag (`DEC-EA-003` for `example-app`). Both forms parse; a register picks one and holds
to it. The tag buys nothing inside the file. It exists because these ids are cited from plans,
backlogs and architecture docs elsewhere in the vault, where a bare `DEC-003` does not say whose
decision it is. Untagged is the default for a new register: the tag is worth its cost only once
a project's decisions are routinely cited from outside it.

```markdown
# Decisions

Architectural decisions binding this project, newest first. Each entry records
what was decided and why. Superseded entries stay — the history is the point.

---

## DEC-007 — Store session tokens in the platform keystore, not app preferences

- **Decided:** 2026-03-20
- **Status:** accepted
- **Domains:** android, security
- **Source:** security review report `review-20260320-1830.md` (local-only)
- **Reason:** App preferences are readable from a device backup, and the review
  showed a restored backup could replay a live session. The keystore keeps the
  key out of backups and ties it to the device. Rejected: encrypting the
  preferences file, which only moves the key problem. Cost: sessions do not
  survive a device migration, so users sign in again.
- **Global:** [[decisions/android#GDEC-AND-003]]
```

### Field semantics

| Field | Required | Meaning |
|-------|----------|---------|
| `Decided` | yes | `YYYY-MM-DD`, the date the decision was taken (not the date it was written down). |
| `Status` | yes | `accepted`, or `superseded by DEC-NNN`. A superseded entry is never deleted or renumbered. |
| `Domains` | yes | Comma-separated domain slugs the decision touches. Drives the domain roll-up. `none` for a decision genuinely specific to this project. |
| `Source` | yes | What produced the decision: a plan file, an architecture doc plus its `ARCH-NN`, a code review, a security review report, or `direct` when taken in conversation. |
| `Reason` | yes | **The point of the register.** The constraint, the evidence, the trade-off accepted, and what was rejected. A `Reason` that only restates the decision is a defect. |
| `Global` | no | Wikilink to the domain entry this rolls up into, `[[decisions/<domain>#GDEC-<DOM>-NNN]]`, present once promoted. `none` (optionally with a reason) is also allowed, to say the decision is project-local and promotion was considered; it parses as no link. |

### Recording a security review recommendation

Security review reports are **local-only and never committed**. A decision that comes from one
therefore:

- cites the report **by filename and date only**, suffixed `(local-only)`;
- restates the finding's substance **in the entry's own words** under `Reason`;
- **never** embeds, quotes at length, or copies the report body into the vault.

The register must stay useful to a reader who cannot open the report (that is what `Reason` is
for) without becoming a second copy of it.

## Projects with no per-project register

The two halves resolve independently, and that asymmetry is load-bearing. `decisions.md` needs
a home, which needs the project's area and name; `Portfolio/decisions/<domain>.md` is keyed by
**domain**, so it resolves from the vault alone.

A project therefore has a defined answer at every stage of its life:

| Project state | Per-project half | Per-domain half |
|---|---|---|
| Unregistered (brand new) | absent — no home yet | **fully readable and binding** |
| Registered, no decisions yet | absent — no `decisions.md` | fully readable and binding |
| Registered with decisions | readable | readable |

**An absent per-project half never means "no decisions apply."** It means this project has
recorded none of its own; whatever its domains bind still binds. A consumer that skips the
lookup because the home did not resolve inverts the register's purpose: the newest codebase,
the one still cheap to change, consults the fewest accumulated constraints.

Registration happens on the normal path: the first plan written with
`records-home.py --for-write` appends the registry entry. So this state ends without a separate
step and **without any new registry field**. Every registry reader would have to tolerate a new
key, so the registry's field set is not a cheap extension point, and an absence needs no field
to represent it.

## Per-domain format

`Portfolio/decisions/<domain>.md` holds `## GDEC-<DOM>-NNN` blocks, where `<DOM>` is a short
uppercase tag for the domain (`AND` for android, `RS` for rust, `UBU` for ubuntu, `IOS`, `MAC`,
`TOR`, …). Numbering is monotonic per domain file. Domain files are created on demand (by
`domain-decisions.py --promote`, which records the tag in the new file's header); the slug list
is open.

Required fields: `Decided`, `Status`, `Reason`, `Applies to`.

```markdown
# Android decisions

Cross-project decisions binding every project on the `android` domain. Ids: `GDEC-AND-NNN`.

---

## GDEC-AND-003 — Session secrets live in the platform keystore

- **Decided:** 2026-03-20
- **Status:** accepted
- **Reason:** App preferences travel with device backups, so any secret kept
  there can be replayed from a restored backup. The keystore keeps keys out of
  backups on every supported version. Accepted cost: secrets do not survive a
  device migration.
- **Applies to:**
  - apps/[[example-app]] (stores its session token there; DEC-007)
  - apps/[[example-wallet]] (signing key must not leave the device; DEC-004)
```

`Applies to` entries are **area-qualified wikilinks** (`<area>/[[<name>]]`), the same form the
global roll-ups use, each with a parenthetical giving the per-project why and the project-side
`DEC-NNN` it pairs with. The why matters for the same reason `integration.md` asks for one: a
bare link says a relationship exists but not what it costs to ignore it.

## Symmetry rule

If a project entry declares `Global: [[decisions/<domain>#GDEC-<DOM>-NNN]]`, that domain entry
MUST list the project under `Applies to`, and vice versa.

`portfolio rebuild` checks every link in both directions after reading all registers. A
one-sided link is listed under `## Asymmetries (review)` in `global-decisions.md` and is **NEVER
auto-fixed**: the user resolves it by editing one of the two files and re-running. A `Global:`
or `Applies to:` link whose target does not resolve to an existing entry, or an `Applies to`
project that has no `decisions.md`, is listed under `## Unresolved targets`.

This is deliberate. Auto-fixing would let the tool invent an `Applies to` edge, and therefore a
claim about a project it has not read, from one side's assertion alone.

## Roll-up

`portfolio rebuild` renders `<vault>/Portfolio/global-decisions.md`:

- `## By domain` — one section per domain file, listing its entries with their status when it
  is not `accepted`, the projects each applies to, and any missing or duplicated field.
- `## By project` — a table of per-project counts (decisions / accepted / superseded / domains),
  each project as an area-qualified wikilink. A project with any malformed entry carries a ⚠️
  beside its count.
- `## Malformed entries (review)` — every flagged project entry, named by project, id (or raw
  heading) and defect: malformed heading, missing field, duplicate field, or a register-level
  error. "Something is wrong with one of twelve decisions" is not an actionable flag.
- `## Asymmetries (review)` — one-sided links, both directions.
- `## Unresolved targets` — links pointing at entries that do not exist, including a GDEC id
  defined in two domain files (an ambiguous target).

It is written only when its content, ignoring `**Last rebuilt:**`, changed, so a rebuild with no
upstream change writes nothing.

## Sidecar

When a project has a `decisions.md`, `portfolio rebuild` adds one pointer line to its repo's
`PORTFOLIO-STATUS` block (`sidecar-format.md`):

```
- **Decisions:** see [decisions.md](<home>/decisions.md)
```

Pointer-only, like every other line in that block: no counts are embedded, because a
repo-committed sidecar lags the vault and an inlined count goes stale the moment a decision
lands.

## Parser rules

The reader in `portfolio-rebuild.py` (`parse_decision_file()`) follows these, and
`../tests/test-portfolio-decisions.py` locks them. `domain-decisions.py` and `compass-scan.py` use
the same reader.

1. **Block boundaries are found with a generic `^## ` match**, and the id shape is checked
   *afterwards*. Boundaries are deliberately NOT found with the strict id regex: a heading that
   misses the em-dash (a plain hyphen is the common slip) would then start no block at all, and
   its body would either be dropped (if it were the first heading) or silently swallowed into
   the previous block's last field. Either way a binding decision disappears, which is the one
   outcome this register exists to prevent.
2. A heading that fails `^DEC-(?:[A-Z]{2,4}-)?\d+ — ` (project) or `^GDEC-[A-Z]+-\d+ — `
   (domain) yields a **flagged entry** carrying the raw heading, not a skipped one, listed under
   `## Malformed entries (review)`. The heading must be repaired before the entry's other fields
   mean anything, so such an entry is excluded from counts, from domain grouping and from
   `last_decided`; a `Global:` link it carries is reported as unresolvable rather than followed.
3. Fields are `- **Name:** value` lines. A field may wrap onto continuation lines, which are
   joined with a single space. A horizontal rule (`---`, `***`, `___`) never joins into a value.
4. A field repeated inside one block keeps the last value and is **flagged** as a duplicate:
   catching exactly that kind of hand-editing slip is the register's job.
5. A block missing a required field is **reported, not dropped**: it appears in the roll-up
   flagged, so a malformed entry is visible rather than silently gone. The compass scan follows
   the same degrade-never-drop contract.
6. A file that cannot be read, or holds no recognizable blocks, contributes zero entries and one
   error line; it never aborts the rebuild.
7. `Domains` values are lowercased and stripped before grouping; `none` expands to no domains
   and is not a malformation.
8. Ids are matched as `DEC-(?:[A-Z]{2,4}-)?\d+` / `GDEC-[A-Z]+-\d+`. Zero-padding to three
   digits is the authoring convention, not a parser requirement: a `DEC-7` parses, it is simply
   not how entries should be written. The project tag is likewise optional (§ Per-project
   format): both `DEC-003` and `DEC-EA-003` parse, and a register uses one form throughout.
9. **An id claimed by two blocks in the same file is reported**: every reference to it is
   ambiguous, and nothing here can know which block the author meant. Both blocks are still
   parsed and listed. (The cross-*file* GDEC case is caught by the symmetry check.)
10. **An `Applies to` wikilink with no `<area>/` prefix is reported** under `## Unresolved
    targets`. A bare `[[name]]` matches neither direction of the symmetry check, so without this
    it would simply not exist as an edge: invisible rather than wrong.
11. **A `Global:` link's domain segment is checked against the register that actually owns the
    GDEC id.** Resolving on the id alone would report a link pointing at a file that does not
    contain the entry as correct.
12. A `## `-prefixed line inside a field's continuation (a Reason quoting a heading, say) is
    read as a block boundary; that is inherent to rule 1. It degrades **visibly**: the quoted
    line becomes a flagged malformed-heading entry and the following decision parses intact, so
    the truncation is reported rather than silent. Avoid `## ` at the start of a continuation
    line; indent it or use inline code.
