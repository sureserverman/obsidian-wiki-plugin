---
description: Review pending session captures the SessionEnd hook flagged
---

Use the `vault-capture-review` skill to list `session-capture` entries the
`obsidian-wiki` SessionEnd hook (`scripts/capture-session.sh`) appended to
`~/dev/knowledge/log.md`, filter out the ones already imported, and let you
pick which to extract via `vault-session-import`.

The hook runs in the background after every Claude Code session ends. It
scores the session via lightweight heuristics and queues a `session-capture`
log entry whenever the score is at or above the threshold (default 2).
**Nothing is extracted at capture time** — extraction is the job of this
review flow, so the user stays in control of what lands in `raw/sessions/`.

**Arguments**: `$ARGUMENTS` — optional control:

- (empty)  → show pending captures, capped at 20 newest, prompt for selection.
- `all`    → show every pending capture with no display cap.
- `<N>`    → show only the top N pending captures by score.

The skill is **read-only** on `log.md` — the only side effect is delegating
to `vault-session-import`, which writes the actual extract and the
`Captured-as:` cross-reference back to the original capture entry.

If the queue is empty, the skill says so and exits — there's nothing to do.
You can lower `OBSIDIAN_WIKI_CAPTURE_THRESHOLD` in your shell to make the
hook more sensitive, or set `OBSIDIAN_WIKI_NO_CAPTURE=1` to disable
auto-capture entirely for the current shell.

**Examples**:
- `/obsidian-wiki:review-captures`
- `/obsidian-wiki:review-captures all`
- `/obsidian-wiki:review-captures 5`
