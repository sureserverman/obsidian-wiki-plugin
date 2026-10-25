# Integration Plan Format

An integration plan coordinates a change that touches several projects, for example "ship
session API v2 in example-api, then move example-app onto it, then retire v1". It differs from
a per-project plan because no single project owns the whole arc, and it differs from an ordinary
vault note because it is operational and multi-project, with stages, dependencies and a status
tracker updated as each stage lands.

No script reads or writes these files. They are authored by hand or by planning's skills, and
`integrate` surfaces them only through the backlog pointers below.

## Directory layout

```
Portfolio/integrations/<arc-name>/
  plan.md      # the coordinated staged plan
  status.md    # which stages are green
```

`<arc-name>` is a kebab-case slug of the arc's theme, e.g. `example-api-sessions-v2`.

## plan.md format

Every `plan.md` begins with YAML frontmatter, followed by a staged body.

### Frontmatter

```yaml
---
arc: <arc-name>
spans:                       # the projects this arc touches
  - "[[example-api]]"
  - "[[example-app]]"
created: <YYYY-MM-DD>
status: active | done | abandoned
---
```

| Field | Meaning |
|---|---|
| `arc` | Matches the directory slug exactly. |
| `spans` | Wikilink list of every project the arc touches. At least two entries. |
| `created` | ISO date the arc was opened. Set once; never updated. |
| `status` | Lifecycle state. `done` when every stage is green; `abandoned` if the arc is cancelled. |

### Body

The body lists stages in execution order. Each stage is owned by one of the spanned projects and
uses the same Stage/Task/Depends-on/Blocks discipline as a planning plan.

Example skeleton:

```
## Stage 1 (example-api): ship session API v2

- Task: add the v2 route handler
- Task: write the migration guide

## Stage 2 (example-app): move to v2   (depends on Stage 1)

- Task: update the client to call the v2 endpoint
- Task: integration smoke test

## Stage 3 (example-api): retire v1     (depends on Stage 2)

- Task: remove the v1 handler
- Task: update the changelog
```

A stage header names its owning project in parentheses. A dependency goes on the header line as
`(depends on Stage N)`.

## status.md format

`status.md` holds a per-stage table that the user (or planning's `executing-plans`) updates as
stages land:

```markdown
# Status: <arc-name>

| Stage | Owner | State | Landed |
|---|---|---|---|
| Stage 1 | example-api | green | 2026-03-10 |
| Stage 2 | example-app | pending | — |
| Stage 3 | example-api | pending | — |
```

Valid states: `pending`, `in-progress`, `green`, `blocked`. `Landed` records the date the stage
was confirmed complete; leave `—` until then.

## Backlog pointer rule

When an arc is created, each project in `spans` receives a pointer entry in its own
`backlog.md`, tagged `integration` and carrying an `Integration:` line, so the project's backlog
shows the cross-project commitment:

```markdown
## BL-NNN — Track arc example-api-sessions-v2

- **Tags:** integration
- **Integration:** plan=example-api-sessions-v2
- **Source:** Portfolio/integrations/example-api-sessions-v2/plan.md
```

`integrate` groups these entries under the arc in `integration-backlog.md`. Add the pointer when
the arc is created, not after its stages are complete.

## Hard rules

- One arc = one directory. Integration plans do not nest.
- `spans` lists at least two projects. A single-project arc is an ordinary plan in
  `Portfolio/<area>/<project>/plans/`.
- `arc` in the frontmatter matches the directory name exactly.
- When an arc reaches `done`, keep `status.md` and the directory where they are, so the history
  stays readable.
