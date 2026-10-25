# `rebuild` — the steps, and the business and security layers

The procedure behind `../SKILL.md` § `rebuild`: regenerate the global roll-ups in the vault and
refresh the repo sidecars. In the default flow this is step 4.

Inputs: optional `--write` (off by default). The vault is resolved and checked before anything
else; an unset or unreachable vault is refused with no fallback. `--write` is refused while
another owner holds the vault's maintenance window.

**The command runs the shipped tool:** `../scripts/portfolio-rebuild.py [--write]`, with
`--write` only when the user typed it. The steps below are its contract.

The roll-ups live only in the vault, at `<vault>/Portfolio/`. There is no second copy anywhere
else.

Operation:

1. Load the registry, enabled projects only, leaving out every `records: repo` entry: it has
   no vault home, so it gets no sidecar block and no roll-up row. A missing registry, YAML that does not parse, a
   file with no `projects:` list, or an entry without string `name`, `area` and `path` is
   refused, never read as an empty or smaller portfolio. Each enabled project's
   `<home>/integration.md`, when present, is read next: one that cannot be read as a
   declaration (`integration-format.md` § Hard rules) refuses the whole run before its first
   write, dry run included, naming each file and why.
2. **Sidecars.** For every enabled project, write the `PORTFOLIO-STATUS` block into
   `<repo>/.claude/vault-context.md` per `sidecar-format.md`, creating the file if absent. The
   vault's `Portfolio/` is re-checked before each project; if it has gone, the remaining
   projects are skipped with a warning rather than writing into a vanished vault. A sidecar
   that cannot be decoded as UTF-8 is skipped, never overwritten.
3. **`global-backlog.md`** per `global-formats.md`: a `### <area>/[[<name>]] — N open` section per
   project whose home has a `backlog.md` with entries, with the backlog's path and its three
   first entry titles. The `<!-- BEGIN PRESERVE -->` … `<!-- END PRESERVE -->` body (the
   hand-curated `## Cross-project items`) is carried over **byte-for-byte**. If that block is
   **ambiguous** (not exactly one sentinel of each kind, sentinels out of order, or the file is
   not valid UTF-8) the write is REFUSED, the file is left untouched, and the report says
   `SKIPPED (ambiguous PRESERVE)`; the other roll-ups still write. Resolve it by hand and
   re-run.
4. **`global-decisions.md`** per `decisions-format.md`: a by-domain index of every
   `Portfolio/decisions/<domain>.md`, a per-project count table (decisions / accepted /
   superseded / domains) from each home's `decisions.md`, and three review sections:
   `Malformed entries (review)`, `Asymmetries (review)`, `Unresolved targets`. A link between a
   project's `Global:` and a domain's `Applies to:` that is one-sided is **reported, never
   auto-fixed**: repairing one side would assert an edge about a project the run has not read.
   A project with no register contributes nothing and is not an error.
5. **`global-maturity.md`**: a row per project that has a `MATURITY.md` in its home, names as
   `[[wikilinks]]`, a cell per axis and a ship-ready verdict (`global-formats.md`).
6. **Business layer (optional, additive).** It runs only when a scanner is configured:
   `$BUSINESS_SCAN_PATH` (a script, run with the same Python), else the `business_scan` argv in
   `~/.config/obsidian-wiki/config.json`. No other plugin is assumed to be installed.
   - The scanner's JSON is piped into `business-rollup.py`, found **beside the scanner's real
     file** (after symlinks are resolved). Naming a scanner trusts its directory: the roll-up
     there runs with this process's rights, and nothing outside that directory is searched.
   - The roll-up's output must start with a `# Global business` heading. A scanner or roll-up
     that fails, times out (120 s each), prints nothing, or prints no such heading leaves any
     existing `global-business.md` **untouched**; the status reads
     `global-business written: None`.
   - With no scanner configured, or the scanner file or its roll-up missing, the status is
     `business layer: unavailable (<why>)` and nothing else changes. Every other output is
     byte-identical either way (`../tests/test-business-degradation.py`).
   - `compass` runs the same scanner and reads its JSON: a `projects` list whose entries carry
     `name`, `assessed`, `verdict`, `monetization.model`, `gtm.pct`,
     `last_reviewed_age_days`, `research` / `plan` (`exists`, `age_days`) and `metrics`; an
     entry with `group: true` applies to the `<area>/<name>` keys in its `members`. Compass
     ignores anything it cannot read, so a broken scanner only switches the layer off.
7. **Security layer (additive).** `../scripts/security-scan.py | ../scripts/security-rollup.py`
   sweeps each enabled project's `<home>/security/history.jsonl` into `global-security.md`:
   open CRITICAL and HIGH, trend, days since the last audit, and the projects never audited.
   Format and input contract: `global-security-format.md`. Three rules it must not break:
   - an unrecorded count renders `?` and **never `0`** (unmeasured is not clean);
   - a `mode: "feeds"` run is flagged `⚠`, because it re-checked dependency advisories without
     running any code lane;
   - `total_open` already includes accepted findings, so "open and not suppressed" is
     `total_open − accepted`.

   If either script is missing the status is `security layer: unavailable (scripts missing)`.
   If one fails, times out, or prints no `# Global security` heading, the status is
   `security layer: failed (global-security.md left untouched)`, any existing file stays
   **intact**, and every other output is byte-identical (`../tests/test-security-degradation.py`).
8. **Report**, one line:
   `sidecars enriched: K | global-backlog written: … | global-maturity written: … | global-decisions written: … | <business status> | <security status> | WRITE|DRY-RUN`.
   Each roll-up is written only when its content, ignoring the `**Last rebuilt:**` line (and a
   first `Generated:` line), changed, so a run with no upstream change writes nothing.

Dry-run renders everything and writes nothing, so the sidecar count is 0. A configured business
layer reports `DRY-RUN` without running; the security scan still runs (it only reads) and
reports `DRY-RUN` when it succeeds.
