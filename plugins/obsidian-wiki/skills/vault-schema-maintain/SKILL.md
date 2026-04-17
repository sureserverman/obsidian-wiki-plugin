---
name: vault-schema-maintain
description: >
  Use when the user wants to update the vault's CLAUDE.md schema, change naming or ingest
  conventions, or mentions "update the wiki schema", "change how ingest works", or
  "the wiki convention is wrong". Trigger on "from now on pages like X go in Y", "the
  ingest rule should be", "actually that convention is wrong", "make this a rule for
  future ingests", or any correction to how the vault categorizes, names, or structures
  pages that should persist across future sessions.
---

> **Vault path:** `<vault>` refers to the path returned by `$CLAUDE_PLUGIN_ROOT/scripts/resolve-vault.sh`. Run it first to resolve the vault location.

# Vault Schema Maintain

Edit the vault's `CLAUDE.md` to evolve its conventions over time. This is the only
skill that is allowed to modify `CLAUDE.md`. All other skills (`vault-ingest`,
`vault-query`, `vault-lint`) read it but never write to it.

The schema is a living document. It captures decisions the user has made about how
their vault works, and it grows as patterns are corrected, edge cases come up, and new
categories or rules are introduced.

## When to edit

Edit `CLAUDE.md` only when one of these is true:

- A rule was **corrected** during a real ingest or query — the user said "actually,
  files like this should go in `Patterns/` not `Architecture/`". That's a permanent
  rule, not a one-off.
- A **new convention** was introduced — frontmatter field, tag taxonomy, naming pattern.
- An **edge case** came up that the existing rules don't cover, and the user articulated
  a new rule for it.
- A rule is **wrong** — the schema says X but the actual vault contradicts it.

Do **not** edit `CLAUDE.md` for:

- One-off notes about a single ingest.
- Speculative rules ("we might want to do this someday").
- Stylistic preferences unless the user explicitly wants them codified.
- Rules you inferred from a single example.

When in doubt, ask the user "do you want this to become a rule, or just for this one
file?" before touching `CLAUDE.md`.

## Edit procedure

1. **Read the current `CLAUDE.md` in full.** You need the section structure and
   existing wording before proposing a change.
2. **Identify the section** the change belongs to. The schema is organized into
   sections like Structure, Naming, Frontmatter, Ingest, Query, Lint, Schema Evolution.
   Each rule belongs in exactly one section.
3. **Write a minimal diff.** Show the user exactly which lines you propose to add,
   remove, or change. Do not rewrite surrounding paragraphs.
4. **Confirm before applying.** Always show the diff and wait for approval. Even small
   schema changes have downstream effects.
5. **Apply the change with the Edit tool**, not by rewriting the whole file.
6. **Append a log entry** (see below).

## What never to do

- **Do not rewrite the whole `CLAUDE.md`.** Edits are surgical.
- **Do not reorder sections.** Existing readers (the user, other skills) rely on
  positions.
- **Do not remove rules the user added manually**, even if they look redundant or
  contradictory. Ask first.
- **Do not invent new sections.** If a rule doesn't fit any existing section, ask the
  user where to put it before adding a section.
- **Do not codify rules from a single example.** A rule needs to apply to a class of
  cases, not one file.

## Log append

After applying a schema change, append to `<vault>/log.md`:

```
## [YYYY-MM-DD] schema | <one-line summary of the rule added or changed>
- Section: <section name>
- Reason: <what prompted the change>
```

The "Reason" line is important — future-you needs to know whether the rule is still
load-bearing.

## Common pitfalls

- **Editing without reading.** You must read `CLAUDE.md` before proposing changes.
- **Batching unrelated changes.** One schema change per edit, one log entry per
  change.
- **Codifying preferences as rules.** "I like it this way today" is not a rule.
- **Skipping confirmation.** Schema changes affect every future ingest and query.
- **Skipping the log append.** The schema's own history lives in `log.md`.
