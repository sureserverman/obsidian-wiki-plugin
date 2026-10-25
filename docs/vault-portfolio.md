# vault-portfolio: setup and configuration

`vault-portfolio` is the cross-project layer for the `planning` plugin. Without it,
planning keeps each project's plans, backlog, decisions and maturity checklist in the
repo, under `<repo>/docs/`. With it, those records live in your Obsidian vault, under
`<vault>/Portfolio/<area>/<name>/`, and the plugin rolls them up across every project:

- `/vault-portfolio:portfolio` — scan the registry, unify backlogs, audit maturity,
  migrate a repo's records into the vault, record cross-project edges, reconcile plan
  status, read and promote per-domain decisions, and rebuild the global dashboards (`global-backlog.md`, `global-maturity.md`, `global-decisions.md`,
  and the optional security and business roll-ups).
- `/vault-portfolio:compass` — what is in flight, what to work on next, and a periodic
  review sweep across the portfolio. It writes nothing itself. When a business scanner is
  configured (below), compass runs it too.

The two plugins meet at one call: planning's **records resolver**.

## Install from a local checkout

The plugin is installed from a checkout of this marketplace and is read from that
checkout, not from a versioned cache:

```text
git clone https://github.com/sureserverman/obsidian-wiki-plugin <checkout>
/plugin marketplace add <checkout>
/plugin install vault-portfolio@obsidian-wiki
```

It needs `python3` with PyYAML and `bash`. `planning@staged-planning` must be installed
too; vault-portfolio adds to planning and does nothing on its own.

## Wire it to planning

Name the resolver in planning's config, `~/.config/staged-planning/config.yaml` (or the
file `$STAGED_PLANNING_CONFIG` names):

```yaml
records_resolver: [python3, <checkout>/plugins/vault-portfolio/scripts/records-home.py]
```

The value is an argv list; each item is `~`-expanded. Without this line planning keeps
using `<repo>/docs`.

## Which vault

The vault is read in this order; the first one set wins:

1. `$OBSIDIAN_VAULT_PATH`. It is used as given, even when it names a missing
   directory: a typo is reported as an unreachable vault, never replaced by a vault
   further down the list.
2. `default_vault` in `~/.config/obsidian-wiki/config.json`, the setting obsidian-wiki
   and vault-context already read.
3. `vault_dir` in `~/.claude/portfolio-config.yaml`, the legacy setting.

With none of them set, the vault is **unconfigured**. vault-portfolio never falls back
to a default vault: a script that writes into a vault does not guess which one.
(obsidian-wiki's own `resolve-vault.sh` falls back to `~/dev/knowledge`; that fallback
is not used here.)

A vault counts as reachable when its path is absolute and it holds a `Portfolio/`
folder. An unmounted mountpoint is an empty directory, so the folder is what tells a
mounted vault from a missing one. Set up a new vault by creating `<vault>/Portfolio/`
once, by hand.

## Where the registry is

The registry lists the projects the portfolio tracks: `path`, `name`, `area`,
`enabled`, and optionally `records: repo`. It is found in this order:

1. the `registry` key in `~/.config/obsidian-wiki/config.json`;
2. `~/.claude/projects-registry.yaml`, if it exists (the legacy location);
3. `~/.config/obsidian-wiki/projects-registry.yaml`.

vault-context reads the same definition, so the two plugins cannot disagree about it.
A registry that is not YAML, has no `projects:` list or holds a malformed entry is
refused with a message naming it, never read as empty. A missing registry is created
by the first write that registers a project: `scan --add … --write`, or the
resolver's first `--for-write`. Until then the readers (`unify`, `rebuild`, `compass`
and the rest) refuse it; the resolver without `--for-write` treats it as an empty list.

To keep one project's records in its repo (for example a public project whose
backlog and decisions belong beside its code), set `records: repo` on its entry and
leave it `enabled: true`. It stays registered, but gets no vault home, and no script
reads a vault folder left at its old path. The resolver exits 3 for it, so planning
uses `<repo>/docs`. `rebuild` writes no sidecar block for it and gives it no roll-up
row. `migrate` and `unify` skip it. `compass` and `plan-status` list it with the
reason. Any other `records` value is refused.

## The resolver's exit codes

`records-home.py --project <abs repo> [--for-write]`:

| Exit | Meaning | planning then |
|---|---|---|
| 0 | stdout is one absolute line, `<vault>/Portfolio/<area>/<name>` | uses that directory |
| 3 | not managed here: no vault is configured, no area/name can be derived, or the entry says `records: repo`; stderr says which | uses `<repo>/docs` |
| 2 | the vault is configured but unreachable, an input does not parse, or a `--for-write` step failed | stops |

Area and name come from the project's registry entry, else from the repo path's last
two segments (`<projects-root>/<area>/<name>`). Exit 2 is never "unmanaged": a vault that has
dropped off its mount is not treated like a machine with no vault.

Without `--for-write` the resolver only reads. With `--for-write` it first checks the
maintenance window, then refuses a grouping folder (a folder of projects rather than a
project), then refuses a home whose `integration.md` cannot be read (exit 2, naming the
file and why, nothing created), then registers the repo if it is not listed, creates the
home and refreshes the repo's `PORTFOLIO-STATUS` block in `.claude/vault-context.md`.
A refusal up to the registry append is exit 2 and leaves everything as it was. After
the append, a home that cannot be created is exit 2 with the entry kept, and a re-run
creates the home. A sidecar block that cannot be written only warns on stderr: the
resolver still exits 0 with the home, and `rebuild --write` refreshes the block later.

`records-home.py --decision-registers --project <abs repo>` lists the existing
`<vault>/Portfolio/decisions/<domain>.md` registers that match the repo's stack or
name the project under an entry's `Applies to`, one per line (exit 0), or exits 3
when none match. A domain no file shows, such as security, reaches a project only
through that `Applies to` link.

`records-home.py --all-homes` takes no other argument and only reads. It prints one
JSON document: the vault, and every registry project with its `name`, `area`, `path`,
`enabled`, `home` (or `null`), `records` (`vault` or `repo`) and the `reason` a home is
`null`. It exits 0 with that JSON, and with no rows when there is no registry yet. It
exits 3 when no vault is configured, still printing the JSON with every home `null`,
and 2 when the vault is unreachable or a config file or the registry does not parse. `/vault-portfolio:portfolio` runs it for the maturity step
and before a decisions promote, so the skill reads homes from it rather than working
them out.

## What the commands may run without asking

Each command's `allowed-tools` grants only exact, read-only command lines, with no
wildcard. `/vault-portfolio:portfolio` runs five lines without a prompt: `_config.py`,
`records-home.py --all-homes`, and the default flow's dry runs of `portfolio-scan.py`,
`portfolio-unify.py` and `portfolio-rebuild.py` with no arguments.
`/vault-portfolio:compass` runs one: `compass-scan.py` with no arguments. Any other
line, every write flag included, goes through Claude Code's normal permission prompt,
and that prompt is where you confirm a write. A command's grants stay in force for the
whole turn, including while the model follows the skill and reads text that came out
of the vault, which is why they cover fixed read-only lines only. Each command refuses
arguments that contain shell syntax (`'`, a backtick, `$`, `;`, `|`, `&`, `<`, `>`, `\`
or a newline) without running anything.

## The business layer (optional)

The rebuild and compass can fold in an external business scanner. Name it as an argv
list under `business_scan` in `~/.config/obsidian-wiki/config.json`:

```json
{ "default_vault": "~/notes", "business_scan": ["python3", "~/tools/business-scan.py"] }
```

`$BUSINESS_SCAN_PATH` (a script, run with the same Python) overrides it. The roll-up is
the `business-rollup.py` beside the scanner; the scanner's directory is trusted. With
neither set the layer is off, and every other roll-up is unchanged.

## The maintenance window

obsidian-wiki can hold the vault's maintenance window while it reorganises pages. Every
vault-portfolio write mode — `--write`, `--fix`, `--restore`, `--for-write` — asks for
write access first, and exits non-zero without writing while another owner holds the
window or a window has expired. Reads are never blocked.
