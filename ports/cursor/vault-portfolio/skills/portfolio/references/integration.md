# Integration — what each neighbouring skill is for

The per-skill detail behind `../../vault-portfolio/SKILL.md` § Integration. Read it when routing an ask to one of
these rather than handling it here. All but `vault-compass` are planning's skills.

- **planning-projects** — writes the plan files that `unify` parses for backlog candidates, into
  the home `records-home.py` resolves.
- **executing-plans** — ticks task and gate status as work lands; `unify` and `plan-status`
  re-read the updated plans.
- **backlog** — owns each project's `backlog.md` format and the `Parked:` annotation; `unify
  --write` appends entries in that format.
- **project-maturity** — invoked per project via sub-agent for `audit` and `get` during
  `maturity`; it owns the axes and the detectors.
- **decisions** — authors the per-project `decisions.md`; this skill's `decisions` subcommand
  owns the per-domain registers, and `rebuild` rolls both up.
- **dispatching-parallel-agents** — the per-project fan-out in `maturity`.
- **vault-compass** — "what should I work on next", "what's in flight" and periodic-review asks go to
  this plugin's `vault-compass` skill, which reads (never writes) the artifacts this skill maintains.
