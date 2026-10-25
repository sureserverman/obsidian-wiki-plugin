# `integrate` — the inter-project roll-up

The procedure behind `../../vault-portfolio/SKILL.md` § `integrate`: roll up inter-project edges and the
integration backlog.

Inputs: optional `--write` (off by default). `--write` is refused while another owner holds the
vault's maintenance window.

**The command runs the shipped tool; never execute these steps by hand.**
`../scripts/portfolio-integrate.py [--write]`, with `--write` only when the user typed it,
implements the procedure: the adjacency, the symmetry check, unresolved targets, the tagged
backlog roll-up and both writes. The numbered steps are that script's contract: read them to
check what a run produced, not to reproduce the work.

1. Read every `integration.md` under `<vault>/Portfolio/` (schema in
   `integration-format.md`). A file's project is its frontmatter `project:`, else its folder
   name. Nothing under the vault folder of a `records: repo` entry is read, here or in the
   backlog roll-up: that folder is not the project's state. A file that cannot be read as a
   declaration (`integration-format.md` § Hard rules)
   refuses the run, dry run included: the script exits non-zero naming each such file and
   why, and writes nothing.
2. Build `Portfolio/integration-graph.md`: the `depends_on → upstream` edge list, then
   `## Asymmetries (review)`. **Symmetry rule:** if A declares `impacts: [[B]]`, B must declare
   `depends_on: [[A]]`, and the other way round. Asymmetries are reported, **never
   auto-fixed**: the user resolves them by editing one side. A target that is not a project
   name in the registry (enabled or not) is listed under `## Unresolved targets` and does not
   block the roll-up.
3. Build `Portfolio/integration-backlog.md`: every `## BL-NNN — <title>` entry in any
   `backlog.md` under `Portfolio/` whose `Tags:` line contains `integration`, or that carries an
   `Integration:` line, grouped under `## edge: <slug>` by the entry's first `edge=<slug>` or
   `plan=<arc>` (else `unspecified`). The items stay in their project's backlog; this file is a
   cross-project view.
4. An integration arc lives under `Portfolio/integrations/<arc>/` (schema in
   `integration-plan-format.md`). Each spanned project's backlog carries an
   `Integration: plan=<arc>` entry, and step 3 is what surfaces it. The script does not read the
   arc's own `plan.md`.

The run prints `edges: N | asymmetries: N | dangling: N | integration-backlog items: N` and each
asymmetry. Dry-run ends with `(dry-run — pass --write to persist)`. With `--write`, each file
is written only when its content (ignoring `**Last rebuilt:**`) changed, and the run reports
`wrote: …` and `unchanged: …`.
