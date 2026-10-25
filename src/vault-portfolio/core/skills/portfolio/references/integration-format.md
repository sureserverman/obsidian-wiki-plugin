# Integration Format: `<vault>/Portfolio/<area>/<project>/integration.md`

A project that takes part in the portfolio's `integrate` op MAY carry an `integration.md` that
declares its inter-project edges: what it depends on upstream and what it can break downstream.
`integrate` reads every such file, merges the edges into one `integration-graph.md`, and
cross-checks their symmetry. This is the Depends-on/Blocks discipline of a single plan, applied
across project boundaries: make every load-bearing relationship visible from both ends, so no
edge is known only to the project that happens to feel it. The file is pure declaration;
`integrate` never rewrites it.

## Format

Each `integration.md` begins with a YAML frontmatter block:

```yaml
---
project: <name>          # the declaring project (slug); defaults to the folder name
depends_on:              # upstreams THIS project relies on
  - target: "[[X]]"      # Obsidian wikilink to the upstream project
    why: <one line>      # what the dependency is (API, schema, shared format, deploy path)
impacts:                 # downstreams a change HERE may break
  - target: "[[Y]]"
    why: <one line>
---
```

Both lists are optional. A leaf project with no known upstreams or downstreams may omit both or
leave them empty. `target` is an Obsidian `[[wikilink]]` whose text is the other project's
registry `name`. Write a `why` on every edge: a one-line summary of what the dependency is (an
API contract, a shared schema, a deploy-time path, an environment assumption). The parser does
not enforce it, and an edge without one renders with an empty reason, which tells a reader
nothing.

## Symmetry rule

If project A declares `impacts: [[B]]`, then B's `integration.md` declares `depends_on: [[A]]`,
and the other way round. `integrate` checks every edge in both directions. Any asymmetry, an
edge declared on one side and missing on the other, is listed under `## Asymmetries (review)` in
`integration-graph.md` and is NEVER auto-fixed. The user resolves the gap by editing one of the
two files and re-running `integrate`.

The reason is the same as inside a plan: if only one side of a dependency is declared, the graph
cannot be walked in both directions. Someone reading B's file would not know that A can break
it; someone reading A's file would not know that B is a consumer. Requiring both sides makes the
full blast radius of a change visible from either end, without tooling inferring intent.

## Body

Below the closing `---`, an `integration.md` may hold free prose with per-edge detail.
Suggested structure:

```
## <TargetProject>

Which exact API endpoint, schema version, or file path is relied upon.
What the version constraint is, if any.
What breaks if the upstream drifts without coordinating a change here.
```

`integrate` does not parse the body. It does not affect the graph or the symmetry check.

## Example

A complete `integration.md` for `example-app`, which consumes `example-api`'s session API and is
in turn deployed by `example-deploy`:

```markdown
---
project: example-app
depends_on:
  - target: "[[example-api]]"
    why: calls example-api's session endpoint to open and refresh user sessions
impacts:
  - target: "[[example-deploy]]"
    why: example-deploy runs example-app's install hook; a signature change breaks it
---

## example-api

Relies on `POST /sessions` as introduced in example-api v0.4. The response schema is
`{token: str, expires: int}`. If example-api renames either field, example-app's login fails
at runtime with no startup check. Coordinate any session-API change with this project.

## example-deploy

example-deploy calls `example-app install --hook post-deploy` with a fixed argument set. Adding
a required flag or changing the exit codes here breaks its pipeline step until its invocation
is updated.
```

With this file present, `integrate` also expects `example-api`'s `integration.md` to declare
`impacts: [[example-app]]` and `example-deploy`'s to declare `depends_on: [[example-app]]`. A
missing declaration on either side is reported as an asymmetry.

A project whose registry entry sets `records: repo` keeps its `integration.md` in the vault
all the same, at the path above: `integrate` reads it, while every other script leaves that
folder alone. Its edges name other projects, which a public repo should not carry.

## Hard rules

- `integration.md` is pure declaration. `integrate` reads it and never rewrites it. Declared
  edges are never changed by tooling, not during roll-up and not during symmetry review.
- A target whose wikilink text is not a project `name` in the registry (enabled or not) is
  listed under `## Unresolved targets` in `integration-graph.md`. It does not block the roll-up;
  every other edge is still processed and the graph is still written.
- Frontmatter is parsed with `yaml.safe_load`. A file that cannot be read as a declaration is
  **refused, never read as "no edges"**: `integrate` and `rebuild` exit non-zero naming the
  file and the reason, in a dry run and under `--write`, and write nothing; `records-home
  --for-write` refuses with exit 2 and creates nothing. Refused: a file that is not UTF-8, no
  frontmatter block, YAML that does not parse, a top level that is not a mapping, a `project`
  that is not a string, a `depends_on` or `impacts` that is not a list, and an edge that is
  neither a string nor a mapping with a string `target`. CRLF line endings, an empty
  frontmatter block and empty lists are fine.
- An edge may also be written as a bare string (`- "[[X]]"`); it then has no `why`. A target
  without the brackets is read as the whole text. `integrate` and the sidecar read edges the
  same way, so the graph and a sidecar never list different edges.
