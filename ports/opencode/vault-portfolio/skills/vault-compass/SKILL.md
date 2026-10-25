---
name: vault-compass
allowed-tools: Read, Glob, Grep
description: >
  Use to decide and organize work across every project in the portfolio — what's in flight, what to work on next, and a periodic review sweep. Triggers on "what should I work on next", "what's in flight", "portfolio review", "what's going stale". Report-only — recommends, never launches work.
  On OpenCode, invoke it by name: /vault-compass, or ask for the vault-compass skill.
---

> **On OpenCode, this skill runs its scanner itself.** An OpenCode command is a prompt:
> `/vault-compass` loads this skill, and nothing runs the scanner and hands you its JSON.
> Wherever this skill says the command runs the scanner, run this one line yourself, once
> per invocation, exactly so (no flags, no `cd`, no pipe, no redirection):
> `python3 <vault-portfolio-plugin>/skills/vault-compass/scripts/compass-scan.py`
> `<vault-portfolio-plugin>` is this plugin's folder, two levels above the base directory
> the skill tool printed for this skill. Keep the scanner's stdout, its stderr and its exit
> status as printed. The mode is the word after `/vault-compass`, or the one the user named
> with this skill: `now`, `next` or `review`, and nothing means `now`. On anything else,
> name the three modes and stop without running the scanner. OpenCode's `permission`
> settings decide whether the line asks the user first. If the line is refused, say so and
> stop. Never answer from memory.

# Compass — portfolio work orchestrator

Answers three questions across every enabled registry project, grounded in evidence rebuilt
fresh each run, with no maintained state to drift:

- **`compass now`** — what is in flight?
- **`compass next`** — what should I work on next?
- **`compass review`** — what needs attention before it rots?

**Announce at start:** "Using the compass skill for a portfolio work sweep."

## Determinism boundary

All evidence comes from ONE run of the deterministic scanner, `scripts/compass-scan.py`,
which the `/vault-compass` command runs before handing over. It prints one JSON
document: `generated`, `vault_dir`, `projects` and `couldnt_assess`. Each
project carries:
- `plans`: one entry per plan under `plans/` in its vault home, nested sets included (the same
  files `unify` and `plan-status` read; `.audit-backups/`, `*-design.md`,
  `*-architecture.md`, `*-done.md`, `README.md` and `backlog.md` are not plans, by the one
  exclusion `unify` uses; masters are tracked through their
  sub-plans), read through the vendored plan parser: `file` (the path under `plans/`),
  `active`, `stage`, `next_task`, `done`, `partial`, `total`, `abandoned`, `abandoned_reason`,
  `completed`, `unmeasurable`, `blocked_gate` and `note`;
- `backlog`: `open`, `parked` and `parked_items`;
- `maturity`: per-axis `done` / `open` / `na` counts and their totals, or `null` without a
  MATURITY.md;
- `decisions`: the decision-register summary, or `null`;
- `dependents` / `depends_on`: edges from `Portfolio/integration-graph.md`, each with its `why`;
- `git`: `last_commit` and `age_days` (UTC), or `null` when the repo has no readable history;
- `errors`: every collector problem for that project.

An entry that sets `records: repo` keeps its records in its repo and has no vault home. It
is not in `projects`: it is in `couldnt_assess` with that reason, and is never read from a
vault folder left at its old path. Say its records live in its repo; it is not a failure.

This skill's job is **judgment only**: ranking, narration and the agenda. Never re-derive facts
the JSON already carries; never present a fact the JSON does not back.

**Views.** `--mode now|next|review` keeps, per project, only the plans that mode reads (`now`: active and noted; `next`: active; `review`: active, noted, abandoned and unmeasurable) and counts the rest by kind in `plans_omitted`; `now` also leaves out a project with no such plan and no error. `--compact` prints one line without null, false or empty fields. `--part N` (with `--part-bytes`, default 24000) prints the projects in parts that each name `part` and `parts`, with `couldnt_assess` in part 1 only. With no flag the document is the whole one above. A host that cuts long tool output reads a mode's view part by part, each part from a fresh run of the same scan.

**No JSON means no report.** The scanner prints nothing on stdout and exits non-zero when the
vault is unset or unreachable or the registry is missing or malformed (exit 1), or when a config
file does not parse (exit 2). Relay its message and stop. "Nothing is in flight" and "the corpus
could not be read" would otherwise look identical.

**Optional business layer.** When an optional external scanner is named by `business_scan` in
`~/.config/obsidian-wiki/config.json` (or by `$BUSINESS_SCAN_PATH`), each project it reports as
assessed also carries a `business` object: `{verdict, model, gtm_pct, last_reviewed_age_days,
research_age_days, plan_age_days, stage}`. `research_age_days` and `plan_age_days` are the ages
of the scanner's market-research and business-plan artifacts, or `null` when that artifact does
not exist. With no scanner configured, or one that fails, no project has a `business` key, and
every business-aware rule below is skipped: compass is unchanged without it. Never invent a
business fact for a project with no `business` key.
A project belonging to a **business group** carries that group's business object plus a
`group: <slug>` key: the verdict, model and targets are the whole group's, not this repo's
alone. Say so when narrating it, and never recommend business work on the member in isolation.
The group itself is not a registry project and has no row of its own.

## Hard rules

- **Report and recommend only.** Never start the recommended work, never invoke another skill to
  execute it, never write under the vault, `~/.claude/` or any repo. The scanner writes
  nothing there, and neither does the skill. The one exception is outside this plugin: when a
  `business_scan` scanner is configured, `compass-scan.py` runs it, and what it does is up to
  it. If a roll-up looks stale, *suggest* `/vault-portfolio rebuild`;
  do not run it.
- **Every recommendation cites its evidence**: the plan file, stage, task, age, maturity gap or
  edge it rests on, e.g. "stage 2 open, last commit 12 days ago" or "2 maturity boxes from
  ship-ready". No vibes.
- **Respect parking.** A backlog entry with a `- **Parked:** <date or reason>` line (planning's
  `backlog` format) is excluded from `next`. Mention parked items only in `review` (with their
  reason), or once their parked-until date has passed.
- **Respect abandonment.** A plan carrying an `**Abandoned:** <date> — <reason>` marker arrives
  with `"abandoned": true` and `"active": false`. Never recommend it in `next`, and never count
  its open tasks as available work. It is suppressed from *recommendation*, not hidden from the
  *board*: it stays listed (in `review`, and in `now` when asked for a full listing) with its
  reason, so abandoning work never makes it invisible. The **marker is the only authoritative
  signal**: a plan whose prose merely says "OBSOLETE — DO NOT IMPLEMENT" arrives active, with a
  `note` advising that the marker is missing. Surface that advisory; do not act on it. Treating
  free prose as a gate would hide live work, the same failure as recommending dead work, only
  quieter.
- **Respect a blocked gate.** `blocked_gate` true keeps a plan active despite every task done
  and a close-out line; its `note` says why. `**Blocked-accepted:**` retires it: that is the
  author's answer, not a defect to raise again.
- **Degrade loudly.** A plan with no task/Status pair the parser could read arrives
  `"unmeasurable": true`, `"active": false`, with a `stage unknown …` note: no stage, no next
  task, no counts. So it is not in-flight work and not in that count. It is still listed, in
  `review`, with its note. A plan with readable open tasks is unaffected and stays active. Every
  project `errors` entry and every `couldnt_assess` project appears in a **"Couldn't assess"**
  footer on every report. Silence is never coverage.

## Error handling

- Scanner exits with `portfolio not configured: …` or `vault unreachable: …` → report that
  verbatim and point to the portfolio skill's configuration (`/vault-portfolio`). Do
  not half-answer from memory.
- Individual project problems (non-git repo, missing path, unreadable file) are already in the
  JSON. Footer them; never drop them.

## `now` — the in-flight board

List projects that have at least one plan with `"active": true`, freshest `git.age_days` first.
Per project: the plan file, current stage, next task (verbatim from `next_task`), done/total, and
`age_days`. Plans with a `note` go on the same board with the note shown. `unmeasurable` plans
are not in flight and belong to `review`; like abandoned ones, they join a full listing when
asked for, in their own separated group with the note. Declared-abandoned plans
(`"abandoned": true`) are not in flight, so they are not on this board by default; when the user
asks for a full listing, include them in a clearly separated "abandoned" group with their reason
rather than omitting them silently. End with the Couldn't-assess footer.

## `next` — ranked recommendations

Rank candidate work items with these signals, in this order:

1. **In-flight momentum** — an open stage on an active plan outranks any new start. Freshest
   active plans first: finish what is started.
2. **Almost shippable** — projects whose `maturity.open` is small (≤2 open boxes) get boosted:
   finishing beats starting.
3. **Unblocking power** — projects with `dependents` get boosted; name who gets unblocked and
   why (the edge's `why`).
4. **Staleness** — a tie-break, not a top-rank driver: among otherwise-equal candidates, surface
   the one rotting longest.
5. **Launch-ready business case** *(only when a `business` field is present)* — a project that
   is almost shippable (signal 2) AND carries `verdict: monetize` or `free-for-reputation` with
   a low `gtm_pct` (0, or no go-to-market plan yet) is a prime launch candidate. Cite it
   concretely: "ship-ready + validated business case (verdict monetize, GTM 0%) — launch next".
   This boosts *shipping something already validated* above a fresh start; it never fires for a
   project with no `business` key.

Only plans with `"abandoned": false` and `"unmeasurable": false` are ranked here; an
unmeasurable plan has no `next_task` to recommend.

Output the top 5–7 as a ranked list, each entry one sentence of recommendation plus one line of
cited evidence. Parked items are excluded (Hard rules). Close with one sentence on what was
deliberately NOT recommended and why (e.g. "12 legacy plans with unknown stages — see review").

## `review` — the cadence sweep

Surface drift, one section each, saying so explicitly when a section is empty:

- **Stalled mid-stage** — active plans whose project's last commit is older than 30 days. This
  is a *staleness inference* from git recency, named apart from the formal `**Abandoned:**`
  marker below on purpose: a stalled plan is still live work that went quiet, and `next` still
  ranks it. Ask whether it should carry the marker; never assume it.
- **Declared abandoned** — plans arriving with `"abandoned": true`, listed with their marker
  reason. `next` excludes them, but they belong here so abandoning work never makes it
  invisible. In the same section, include plans carrying the missing-marker advisory `note`
  (banner prose, no marker): these are still active and still ranked, and the ask is for the
  author to add the marker or drop the banner.
- **Legacy / unmeasurable plans** — `"unmeasurable": true`, with their note. `next` never ranks
  them (it names them only in its closing line), so this is where they are actually listed. Ask
  the author for an `**Abandoned:**` marker if the plan is dead, or task `- **Status:**` fields if
  it is live; never infer which. If the plan already carries an `**Abandoned:**` marker, no ask
  is needed.
- **Stale backlogs** — projects with open backlog items and no commit in 60+ days.
- **Ship-ready but unshipped** — `maturity.open` of 0 with no release evidence in recent plans.
- **Parked items due** — `Parked:` dates in the past, with their reasons.
- **Decision register cleanup** — projects whose `decisions.malformed` is above 0 (§ Decision
  register).
- **Stale business review** *(only when `business` fields are present)* — projects whose
  `business.last_reviewed_age_days` exceeds ~90: the verdict and targets may be out of date.
  Suggest a re-assessment with whatever tool produced them.
- **Stale business evidence** *(only when `business` fields are present)* — projects whose
  `business.research_age_days` or `business.plan_age_days` is above 90: the market research or
  the business plan is ageing; suggest refreshing it. It fires only for an artifact that exists
  (a `null` age is no nag).
- **No business case** *(only when a business scanner is configured)* — enabled projects with no
  `business` key at all: a commercial triage gap. Omit this section entirely when no project
  has a `business` key, rather than flagging every project.
- **Stale roll-ups** — if the `**Last rebuilt:**` dates of `global-backlog.md` /
  `global-maturity.md` predate the newest plan activity, suggest
  `/vault-portfolio rebuild` (never run it).
- **Couldn't assess** — the footer, always.

End with a **focused agenda**: 3 items at most, drawn from the three views, each with its
evidence line.

## Decision register

When a project's home holds a `decisions.md`, its scan entry has a `decisions` object:
`{count, malformed, domains, last_decided}`. The register format is `decisions-format.md` in
the portfolio skill's references. `count` and `domains` cover only well-formed entries;
`malformed` counts entries the parser flagged: a bad heading, a missing required field, a
duplicated field. A project without a register has `decisions: null`, which is the normal case
and never a finding.

Use it two ways, and only these two:

- **`review` — surface `malformed > 0`** as a cleanup item, citing the count. The value of the
  register is that a binding decision is never silently lost, so a flagged entry nobody looks at
  defeats the point. `global-decisions.md` names each one.
- **`next` / `now` — treat decisions as context, never as work.** A register is not a backlog,
  and a project is not more urgent for having one. Where a recommendation touches an area a
  decision binds (its `domains` overlap the work), say so and cite the register, so the work
  starts from the constraint instead of rediscovering it.

Never infer that a project *needs* a decision recorded from the absence of a register. Most
projects legitimately have none; manufacturing that finding across a whole portfolio is noise,
and the rule against presenting facts the JSON does not back applies here too.

## Integration

- **portfolio** (this plugin) — maintains the artifacts compass reads (registry, roll-ups,
  integration graph); compass never writes them. Rebuild suggestions route there.
- **backlog** (planning) — owns the `Parked:` annotation compass respects.
- **executing-plans / planning-projects** (planning) — where the user goes AFTER picking a
  recommendation; compass itself never invokes them.
- **project-maturity** (planning) — produces the MATURITY.md files behind the almost-shippable
  signal.
- **An optional business scanner** — when `business_scan` names one, it supplies the per-project
  `business` object behind the launch-ready and business-review signals. Compass reads it
  through the same single scan and never writes it. Without one, those signals are silently
  unused.

## Remember

- One scanner run per invocation, by the command; judgment on top; no writes anywhere.
- Cite evidence on every recommendation; footer every gap in coverage.
- Momentum > almost shippable > unblocking > staleness.
- Parked means parked until the date says otherwise.
