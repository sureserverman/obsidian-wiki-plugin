# Extraction classification — what `../SKILL.md` keeps, and what lives in a reference

`../SKILL.md` is a trunk: it is read on every invocation, so it carries what binds every run and
points at references for the rest. This file records which of its sections are which, and the
rules for changing that. Read it before moving text between the trunk and a reference, in
either direction.

## Three classes

- **unconditional** — binds every run, whatever was invoked. Stays in the trunk whole.
- **rule+elaboration** — the rule binds every run; its justification does not. The rule stays in
  the trunk; the justification may move to the reference that owns the subject.
- **conditional** — read only when one branch is taken. Moves to a reference, and leaves a
  pointer in the trunk.

## This trunk is a dispatcher

A skill read top to bottom as one procedure has little conditional material. `portfolio` is the
other shape: eight subcommands, of which an explicit invocation runs exactly one. Per-branch
procedure consulted only when that branch is taken is the textbook `conditional` case, so most
of the bytes live in `subcommand-*.md`.

The honest qualification: **the default flow (no subcommand) runs `scan` → `unify` →
`maturity` → `rebuild`**, so a default invocation reads four subcommand references, not one.
The real shape is *a trunk plus four reads on a default run, or exactly one read on an explicit
subcommand*. A named-subcommand invocation, the common case for `migrate`, `integrate`,
`plan-status` and `decisions`, gets the full saving.

## A pointer keeps the rule that binds when its reference is never opened

A dispatcher's branches are where the destructive behaviour lives. So each subcommand pointer in
the trunk keeps at least one rule that binds even when its reference is never opened:

| Pointer | The rule it keeps in the trunk |
|---|---|
| `scan` | seeds the registry and exits; changes the registry only on the user's typed `--write` |
| `unify` | never writes during dry-run |
| `maturity` | a project without MATURITY.md is skipped, not scaffolded |
| `migrate` | copy → verify → delete; a populated home is skipped, never overwritten or merged |
| `integrate` | asymmetries are reported, never auto-fixed |
| `rebuild` | the PRESERVE block survives byte-for-byte; a failed layer never truncates a roll-up; unmeasured renders `?`, never `0` |
| `plan-status` | report-first; out-of-contract markers are never candidates; `**Abandoned:**` is never inferred |
| `decisions` | superseded marked not filtered, malformed flagged not dropped; both link directions or neither |

Leaving such a rule as a noun inside a pointer sentence ("see the migrate procedure") loses it
on every run that does not open the reference. A pointer that names what the subcommand does,
gates its writes, carries its invariants and cites its file has a roughly fixed cost, whatever
the size of the procedure behind it. **Size a conditional section as a fixed amount per pointer,
not as a percentage of its bytes**, and size the reference map by its row count.

**Never move an obligation to hit a size target.** If a cut lands larger than estimated, record
the miss and re-derive the estimate.

## The table

### unconditional

| Section | Why it stays |
|---|---|
| Where things resolve (read this before any read or write) | its heading says read before any read or write; the no-silent-fallback and unreachable-vault rules guard every write |
| Reference map | the index; without it no reference is reachable, so it can never become a pointer itself |
| Subcommands | section header and the one-of-eight dispatch rule |
| File conflicts and write discipline | the write surfaces and the one-path-per-agent rule bind every subcommand |
| Hard rules | dry-run default, the 8-in-flight cap, `enabled: false` exclusion: every run |

### rule+elaboration

| Section | Rule kept | Elaboration moved |
|---|---|---|
| Default flow (no subcommand, or explicit `portfolio` invocation) | the four-op order, the dry run before any mutation, the idempotency guarantee | per-op detail, into the opening sentence of each subcommand reference |
| Staged rollout | `--include-maturity` gates maturity in the default flow | why the gate exists, into `subcommand-maturity.md` |
| Configuration | the key list, the vault order, and that unset and unreachable get the same refusal | nothing: the key list and the missing-setting rule are the section; there is no justification layer under it to shed |

### conditional

| Section | Destination |
|---|---|
| `scan` procedure | `subcommand-scan.md` |
| `unify` procedure | `subcommand-unify.md` |
| `maturity` procedure and the gate's rationale | `subcommand-maturity.md` |
| `migrate` procedure and rollback | `subcommand-migrate.md` |
| `integrate` procedure | `subcommand-integrate.md` |
| `rebuild` steps and the business/security layers | `subcommand-rebuild.md` |
| `plan-status` classification and evidence grades | `subcommand-plan-status.md` |
| `decisions` operations | `subcommand-decisions.md` |
| Integration (what each neighbouring skill is for) | `integration.md` |
| Remember | nowhere: it restates the trunk's own rules and stays whole. Deleting a restatement is a decision for the skill's owner, not a side effect of a cut |

## Phrases that must stay in the trunk

A heading over a pointer satisfies "the section still exists" perfectly and loses the rule. So
each binding row names a phrase that must stay in `../SKILL.md` after any cut. Check them by
grep before and after an edit; a conditional row is exempt, because its pointer is what moved.

| Section | Must appear in the trunk |
|---|---|
| Reference map | These load when their condition is met |
| Where things resolve | No silent fallback |
| Where things resolve | fails loudly |
| Where things resolve | A missing vault is not an empty vault |
| Subcommands | An explicit invocation runs exactly one |
| Subcommands | composes four, one of them gated |
| Subcommands | Each procedure lives in its own reference |
| Default flow | Idempotency guarantee |
| Default flow | Confirms with the user before any mutation |
| Staged rollout | skips the maturity step UNLESS |
| Staged rollout | works normally |
| Configuration | never a fallback |
| Configuration | Every key is optional |
| Configuration | the same refusal |
| File conflicts and write discipline | no two agents touch the same path |
| Hard rules | Dry-run is the default for every write-capable subcommand |
| Hard rules | non-negotiable |
| Hard rules | are excluded from |

**A phrase that outlives its decision is as wrong as a pointer that outlives its destination.**
When a rule changes, replace its phrase with one that pins the new rule, in the same change;
never just delete it, because deleting a phrase silences the check as surely as keeping a stale
rule would.
