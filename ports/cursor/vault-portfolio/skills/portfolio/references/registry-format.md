# Registry Format

The registry is the list of every project the portfolio tracks. Its location is the `registry`
key in `~/.config/obsidian-wiki/config.json`, else `~/.claude/projects-registry.yaml` when that
file exists, else `~/.config/obsidian-wiki/projects-registry.yaml`.
`<vault-portfolio-plugin>/skills/portfolio/scripts/_config.py` prints the path in use. The
vault-context plugin resolves the same path through the same definition (a byte-identical copy
of `<vault-portfolio-plugin>/scripts/lib/registry_path.py`), so the two plugins cannot disagree about it.

The `scan` subcommand seeds it on first run by walking `<projects-root>/`, and every later edit
it makes waits for the user's typed `scan --write`. The only other writer is
`records-home.py --for-write`, which appends an entry for a project being planned for the first
time (§ The records home). When no registry exists yet, the first such append creates it, as
the first `scan --write` addition does. `records-home.py` reads a missing registry as one with
no entries (`--all-homes` prints no rows), and `scan` treats it as a first run
(`subcommand-scan.md`). Every other script refuses a missing one.

## Schema

### Top-level fields

| Field | Type | Meaning |
|---|---|---|
| `version` | integer | Schema version. Currently `1`. |
| `projects` | list | Project entries. Order is informational; uniqueness is by `path`. |

### Per-entry fields

| Field | Type | Meaning |
|---|---|---|
| `path` | string | Absolute path to the project root, with `~` already expanded, e.g. `/path/to/dev/apps/example-app`. Required. |
| `name` | slug (string) | Kebab-case identifier, the final path component. Required. It may collide across areas; uniqueness is by `path`. |
| `area` | string | The category directory under `<projects-root>/` holding the project, e.g. `apps`. It is the `<area>` in `<vault>/Portfolio/<area>/<name>/`. Required. |
| `enabled` | boolean | `true` (the default when absent) includes the project in `unify`, `maturity`, `migrate`, `rebuild`, `compass` and the security sweep. `false` keeps it listed but skipped. Use it for archived or on-hold projects. |
| `added` | string | ISO date (`YYYY-MM-DD`) the entry was first written. Set once; never updated. |
| `records` | string | Optional. `repo` opts the project out of the vault, as a public project keeps its backlog and decisions beside its code. It is meant for an `enabled: true` entry: the project stays registered, so `scan` does not report it as drift, but it gets no vault home, and no script reads a vault folder left at its old path. `records-home.py` exits 3 for it and planning keeps its records in `<repo>/docs`; `rebuild` writes no sidecar block for it and gives it no roll-up row; `migrate` and `unify` skip it, and refuse it by `--project`; `compass` and `plan-status` list it with the reason; a `decisions --promote` for it needs `--home`. Any other value is refused by the registry validator, never guessed at. |

## Example

```yaml
version: 1

projects:
  - path: /path/to/dev/apps/example-app
    name: example-app
    area: apps
    enabled: true
    added: 2026-01-15

  - path: /path/to/dev/tools/example-cli
    name: example-cli
    area: tools
    enabled: true
    added: 2026-02-10
    records: repo

  - path: /path/to/dev/tools/example-lib
    name: example-lib
    area: tools
    enabled: false
    added: 2026-03-01
```

`example-cli` is a public project: it stays tracked and enabled, and keeps its plans, backlog
and decisions in its own `docs/`. `example-lib` is on hold: `scan` lists it, and the other subcommands skip it.

## Hard rules

- The file is YAML, parsed with `yaml.safe_load`. Keep it plain: no anchors, no aliases.
- Never rewrite the file in bulk. Only append entries, remove specific ones, or toggle
  `enabled`. Full rewrites destroy the diff legibility that makes the registry auditable.
- `name` is informational. Two projects in different areas may share a `name`; uniqueness is
  by `path` alone. Two entries sharing an `area` and `name` would share a vault home, so avoid
  that.
- **A registry that cannot be used is refused, never read as empty or partial.** Every script
  reads it through `load_projects()` in `../scripts/portfolio-rebuild.py`, the one validator.
  A missing file (outside the cases in the opening section), YAML that does not parse, no
  `projects:` list, or an entry without string `name`, `area` and `path` stops the run with a one-line `portfolio not configured: project
  registry … ` message naming the problem (and the entry's position, for a bad entry). A
  roll-up regenerated from zero projects would replace every row with nothing, and a silently
  smaller list is the same wrong answer, only partial. Never auto-repair the file. To start
  over, move it aside (`mv <registry>{,.bad}`) and run `scan` to seed it again.

## The records home: repo → vault home

A registered repo at `<projects-root>/<area>/<project>` keeps its operational docs at:

```
<vault>/Portfolio/<area>/<name>/
```

- The vault is `$OBSIDIAN_VAULT_PATH`, else `default_vault` in
  `~/.config/obsidian-wiki/config.json`, else the legacy `vault_dir` in
  `~/.claude/portfolio-config.yaml`. That order is the only authority for the vault root, and
  it is the one place this plugin differs from obsidian-wiki's own lookup: with nothing set,
  obsidian-wiki falls back to `~/dev/knowledge`, while a script here that writes into the vault
  never guesses which vault that is.
- `<area>` and `<name>` come from the project's registry entry. For a project with no entry,
  they are the last two segments of its path, `<projects-root>/<area>/<name>`.

Example: `<projects-root>/apps/example-app` → `<vault>/Portfolio/apps/example-app/`.

### The resolver

`python3 <vault-portfolio-plugin>/scripts/records-home.py --project <abs repo> [--for-write]` is
the one implementation of that mapping. Planning calls it through its `records_resolver`
setting. This skill never runs it: the `/vault-portfolio` command runs
`records-home.py --all-homes` (below) and hands the skill its JSON, and nothing derives a home
in prose. The `--project` exits:

| Exit | Meaning | stdout |
|---|---|---|
| 0 | the home | one absolute line, `<vault>/Portfolio/<area>/<name>` |
| 3 | not managed here: the vault is unset, no area and name can be derived, or the entry carries `records: repo`. stderr says which. The caller uses `<repo>/docs`. | nothing |
| 2 | the vault is set but unreachable (`vault_problem()`), something could not be parsed, or a `--for-write` step failed (see below for what is left behind). | nothing |

- **Without `--for-write`** it reads only and creates nothing.
- **With `--for-write`** it first calls the vault's `require_write_access()`, then refuses a
  grouping folder (a directory that holds projects rather than being one) with exit 2, using
  vault-context's own containment check. Then it appends the registry entry if absent (`path`,
  `name`, `area`, `enabled: true`, `added`), creates the home, and refreshes the repo's
  `PORTFOLIO-STATUS` block. The append holds a lock on the registry's folder, keeps the old
  bytes as a prefix of the new file, and is refused (exit 2, with the entry to add by hand)
  when it cannot append without rewriting. **Every refusal up to the append is exit 2 and
  leaves everything as it was.** After the append, a home that cannot be created is exit 2,
  with the entry kept; a re-run creates the home. A sidecar block that cannot be written is
  a warning on stderr: the run still exits 0 with the home, and `rebuild --write` refreshes
  the block later. A `records: repo` entry is honored here too: nothing is created or
  registered, and the exit is 3.
- `--for-write` and `--decision-registers` are exclusive. A `records` value other than `repo`
  is refused by the registry validator, here as exit 2.
- **`--decision-registers --project <abs repo>`** prints, one per line and sorted, every
  existing `<vault>/Portfolio/decisions/<domain>.md` whose slug the repo's files point at
  (`domain-slugs.md`), or which names the project's `<area>/[[<name>]]` under an entry's
  `Applies to`. It exits 3 when there are none, when the vault is unset or the entry
  carries `records: repo`, and 2 when the vault is unreachable or a register cannot be
  read. It is read-only.
- **`--all-homes`** takes no other argument and only reads. It prints one JSON document,
  `{"vault": …, "projects": [...]}`, with one item per registry entry: `name`, `area`,
  `path`, `enabled`, `home` (the absolute home, or `null`), `records` (`vault` or `repo`) and
  `reason` (why `home` is `null`, else `null`). A `records: repo` entry, an entry the
  single-project mode would refuse, and an unconfigured vault each give a `null` home with the
  reason. It exits 0 with that JSON (no registry yet is 0 with no rows); 3 when the vault is
  not configured, still printing the JSON with `"vault": null` and every home `null`; and 2,
  with nothing on stdout, when the vault is unreachable or a config file or the registry does
  not parse. This is the call the command makes for the skill, under an exact, read-only
  grant.

Exit 3 means "not managed here", never "unreachable". An unreachable vault is exit 2, and the
caller must stop rather than write into the repo: writing there would hide a dropped mount
behind a warning nobody reads.

### What lives under a project's home

| Path (relative to the home) | Contents |
|---|---|
| `plans/` | The project's plans, written there by planning or moved from `<repo>/docs/plans/` by `migrate`. |
| `backlog.md` | The backlog, moved from `<repo>/docs/backlog.md` or born here on the first `unify --write`. |
| `MATURITY.md` | The maturity checklist. |
| `decisions.md` | The per-project decisions register (`decisions-format.md`). |
| `integration.md` | Declared inter-project edges (`integration-format.md`). |
| `security/history.jsonl` | A security-audit tool's run history (`global-security-format.md`). |

### The sidecar

Each enabled project's `<repo>/.claude/vault-context.md` carries a `PORTFOLIO-STATUS` block
whose `**Home:**` line names the home (`sidecar-format.md`). It lets a session opened in the
repo find its home without asking the registry. It is a **cache**: the registry plus the mapping
above is authoritative, and `rebuild` rewrites the block from them.

### No silent fallback

If no vault is set, every script that would resolve a home **refuses**. The subcommand scripts
print a message starting `portfolio not configured:` and exit non-zero. `records-home.py` exits
3 instead, with stderr saying the vault is not configured, because for planning that is "not
managed here": planning then keeps that project's records in `<repo>/docs`, which is planning's
rule. No script here falls back to writing into `<repo>/docs/`: that would scatter again the
docs this layout gathers in one place.

The same rule binds a vault that is **set but unreachable** (unmounted, stale path, typo,
relative path, or no `Portfolio/` inside). It is refused on the same terms, with a message
naming the path and where it was set:

```
vault unreachable: vault <path> (from <source>) is not an existing directory — refusing, because a missing vault is not an empty vault. Mount the vault or correct the setting.
```

A path handed in on the command line (`plan-status-audit.py --vault`) gets the identical check:
the flag bypasses the config, and must not thereby bypass the rule.

### Creating a home on first write

A registered project whose home does not exist yet gets `<area>/<name>/` created under
`Portfolio/` on the first write. Onboarding a new **project** therefore needs no manual vault
step.

Onboarding a new **vault** does: `Portfolio/` itself is never created by a script, because a
vault without it looks exactly like an unmounted mountpoint, which `vault_problem()` refuses.
Create it once, by hand.

**What bounds that, and what does not.** Homes are created only beneath a *reachable* vault:
absolute, existing, and **containing `Portfolio/`**. An existence check alone cannot see the
dangerous case: a mountpoint is a directory whether or not anything is mounted on it, so an
unmounted vault passes, and `mkdir -p` happily builds a phantom tree there and moves a repo's
only docs into it. The `Portfolio/` clause is what closes that.

The check runs once per run, and the writes follow it. A vault that disappears in between (a
network mount dropping mid-run) is re-checked at the write boundaries: `rebuild` before each
project's sidecar and `migrate` before each project's copy, both by the same `Portfolio/` stat.
That narrows the window to one project's writes; it does not close it.
