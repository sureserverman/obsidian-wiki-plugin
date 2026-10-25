# `decisions` — the per-domain half of the decisions register

The procedure behind `../SKILL.md` § `decisions`. The register answers *why the architecture is
the way it is*, long after the plan that decided it has been archived. It has two halves:

- **Per-project:** `<home>/decisions.md`, `DEC-NNN` entries binding one project. Recording,
  listing and superseding them is planning's `decisions` skill.
- **Per-domain:** `<vault>/Portfolio/decisions/<domain>.md`, `GDEC-<TAG>-NNN` entries binding
  every project on one platform or stack. That half is this subcommand.

The two are linked in both directions, and `rebuild` symmetry-checks the links. The full format
(block grammar, field semantics, symmetry rule, parser rules) is `decisions-format.md`. **Read
it before writing any entry**; this file covers the operations, not the format.

**The command runs the shipped tool,** `../scripts/domain-decisions.py`, with the flags the user
typed after `/vault-portfolio decisions`. It reads registers with the same parser `rebuild` uses, so its digest cannot disagree with
`global-decisions.md`.

## A project not yet in the registry

A brand-new project has no registry entry and no home, so it has no `decisions.md` to read.
That is a supported state, and it is the state in which the register matters most. The halves
resolve independently:

- **The per-domain half needs only the vault.** A domain register is keyed by domain, not by
  project, so it is reachable with no registry entry at all. A greenfield app inherits every
  constraint its platform's register holds before it has written a line of code.
- **Only the per-project half is missing**, and a project that has made no decisions has
  nothing to miss.

So the domain digest is authoritative and sufficient here. Never skip the decisions lookup
because a project has no home: that would make the project with the least local context
consult the fewest constraints. The state ends on the normal path: the first plan resolved
with `records-home.py --for-write` registers the project, and its home exists from then on.

## Operations

All of them need a reachable vault except `--infer-domains`. Exit codes: 0 done; 1 a promote
precondition does not hold (nothing written); 2 usage, config, an unset or unreachable vault, or
a write refused by another owner's maintenance window. `--format json` gives the
machine-readable form of each listing.

### `--list-domains` — which registers exist

Prints one line per `Portfolio/decisions/*.md`: the slug, its entry count and, when there are
any, how many register errors it has. With no registers it says so. Have it run before concluding a
domain has no decisions: a slug with no register is a complete answer, not a failure to look.

### `--domains <slug,...>` — digest what binds a project

The question a planner and an executor ask: *which recorded decisions constrain the work in
front of me?*

1. **Pick the slugs.** `--infer-domains <repo>` prints the slugs `domain-slugs.md` infers from
   the repo's files (one per line, or a JSON list). Add any slug the work itself shows that no
   file does. When the stack is ambiguous, pass every plausible slug: an extra register costs
   one read, a missed one costs a violated constraint nobody catches until review.
2. **The command runs** `domain-decisions.py --domains <slugs> [--format json]`. It digests exactly the named
   registers and no others, in the order asked. Each row carries id, title, status, the
   Reason's first sentence and `Applies to`.
3. **Read the digest as-is.** Superseded entries come back **marked, not filtered**: "we
   believed X and stopped" is what keeps the rejected approach from being proposed again.
   Malformed blocks come back **flagged, not dropped**: a decision that fails to parse is the
   one to look at.

An unknown slug is never silently empty. It is listed under `unknown_domains` in the JSON and
reported on stderr with the slugs that do exist. "No decisions bind this" and "you asked about a
register that does not exist" are different answers. The JSON has the same `extra` shape as
planning's per-repo digest (a list of `{path, rows, errors}`), so one reader handles both.

### `--promote <DEC-NNN>` — lift a project decision into its domain register

Inputs: `--area <area> --name <name>` (the project's registry entry; `--home <dir>` overrides
where its `decisions.md` is), and either:
- `--domain <slug> --reason "<generalized reason>"` for a new domain entry (optional
  `--title`, `--tag` for a new register's id tag, `--why` for the `Applies to` note), or
- `--global <GDEC-ID>` to attach the project to an existing domain entry.

Before a promote, the command runs `records-home.py --all-homes`. Check the typed `--area` and
`--name` against the project's entry in that JSON, and when you name a command line with
`--home`, take the value from the entry's `home` field. Never derive a home in prose. A project
whose `home` is `null` there (a `records: repo` entry) keeps its `decisions.md` in its repo.
The script refuses to derive a vault home for it, so a promote for it needs `--home` naming
the folder that holds that `decisions.md`, typed by the user.

This is the operation that makes a decision *architectural* rather than local. It writes
**both** link directions in one step, which is why it exists rather than two hand edits.

1. Read the project entry. Refuse (exit 1) if it is absent, if its id is claimed by two blocks,
   or if it already carries a `Global:` line: re-promotion is a supersede, not a second
   promotion.
2. **New entry:** take the next `GDEC-<TAG>-NNN` in `<domain>.md` (max + 1, never reused). The
   tag is the register's established one; a new register derives it from the slug unless
   `--tag` names it, and records it in its header. Carry `Decided` from the project entry
   (refuse if it has none), set `Status: accepted`, and use `--reason` as the Reason.
   **The domain Reason must be generalized**: it states the constraint so it holds for every
   project on that domain, not just the originating one. If it cannot be generalized, the
   decision is project-local and should not be promoted.
3. **Existing entry (`--global`):** refuse if the id is in no register or in two, if `--domain`
   names a different register, or if the entry already lists the project.
4. Add the project to the entry's `Applies to:` as `<area>/[[<name>]] (<why>; DEC-NNN)`, using
   `--why` or the project entry's Reason condensed to one line.
5. Add `- **Global:** [[decisions/<domain>#GDEC-<TAG>-NNN]]` to the project entry.

Without `--write` it prints both edits as unified diffs and writes nothing. Show them, and name
the same command line with `--write` for the user to type. With `--write` it
checks the maintenance window first, re-checks that the vault is still there, and writes each
file atomically. Every refusal happens before anything is written, and every other byte of
both files is kept.

## Recording a decision sourced from a security review

Security review is a common producer of architectural decisions, and its reports are
local-only: they are never committed and never copied into the vault. So an entry sourced from
one:

- sets `Source:` to the report's **filename and date only**, suffixed `(local-only)`;
- restates the finding's substance **in the entry's own words** under `Reason`: what the
  exposure was, what constraint it imposes, what was accepted;
- **never** pastes, quotes at length or summarizes the report body into the vault, and never
  reproduces exploit detail.

The test is whether the entry is useful to a reader who cannot open the report. Set `Domains:`
from the finding's scope, not the project's stack (`domain-slugs.md` § `security`).

## Safety rails

- Both registers are hand-authored declaration files. Edit discrete blocks; never rewrite a
  file whole.
- **Never delete an entry.** Decisions are superseded, not removed. The register's value is
  cumulative.
- Never auto-fix a link asymmetry the roll-up reports. Fixing it means asserting something about
  a project you have not read; the user resolves it.
- Never write a report body, credential or exploit detail into the vault.
