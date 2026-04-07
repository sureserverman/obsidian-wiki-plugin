---
name: vault-capture-review
description: >
  Use when the user asks to review pending session captures, asks "what did the
  hook flag", asks to triage auto-captured Claude Code sessions, mentions
  "/obsidian-wiki:review-captures", asks "what's queued in the capture log", or
  wants to see which sessions the SessionEnd hook queued for vault review.
  Trigger on phrases like "review captures", "show pending captures", "what got
  auto-captured", or "import the flagged sessions".
---

# Vault Capture Review

Surface `session-capture` entries that the `obsidian-wiki` SessionEnd hook
(`scripts/capture-session.sh`) wrote to `<vault>/log.md`, filter out the ones
already imported, and let the user pick which to extract via
`vault-session-import`.

This skill is **the consumer** of the capture queue. The producer is the hook —
it appends one log entry per vault-worthy session as the session ends. This
skill never writes to `log.md` directly; it reads, filters, and delegates.

## Step 1 — Read the log

Read `~/dev/knowledge/log.md` (or `$OBSIDIAN_VAULT_PATH/log.md` if set).

Find every entry whose heading matches:

```
## [YYYY-MM-DD] session-capture | <topic>
```

Each entry has a fixed bullet body written by the hook:

```
- Tool: claude-code
- Session: <short-id>
- Transcript: <absolute path>
- Cwd: <project path>
- Score: <int>
- Turns: <int>
- Reason: <hook reason>
- Status: pending
```

If no `session-capture` entries exist, tell the user: "No pending captures.
The SessionEnd hook will queue vault-worthy sessions automatically — come
back later, or lower `OBSIDIAN_WIKI_CAPTURE_THRESHOLD` if you expect more."

## Step 2 — Filter out already-imported captures

For each capture entry, scan **forward** in the log for a later
`session-import` entry whose body contains a `Captured-as:` line referencing
this capture's date and short-id. The cross-reference format is:

```
- Captured-as: [<YYYY-MM-DD>] session-capture <short-id>
```

If a matching `session-import` entry exists, the capture is **already
imported** — skip it.

This is the only way to tell imported from pending: the log is append-only,
so we never edit the capture entry to mark it done. The capture entry stays
in place forever as a historical breadcrumb; the cross-ref on the import
entry is what links them.

Also check the older idempotency rule from `vault-session-import`: does
`raw/sessions/claude-code-<date>-<short-id>.md` already exist? If it does
but no `Captured-as:` cross-ref points to this capture, the import was done
manually — still treat it as imported, but warn the user the cross-ref is
missing.

## Step 3 — Present pending captures to the user

Group by score, newest first within each group. For each pending capture,
show:

- **Topic** (the heading after `session-capture |`)
- **Date** (from the heading)
- **Score / Turns** (from the body)
- **Cwd** basename (the project where the session ran)
- **Reason** (the hook input reason — usually `prompt_input_exit` or `logout`)

Cap the display at 20 captures. If more exist, say "+ N more older captures
hidden — re-run with `all` to see them" at the bottom.

Format:

```markdown
# Pending session captures (N)

## High value (score ≥ 4)

1. **2026-04-07 — Tor bridge bootstrap debugging** (score 5, 87 turns)
   - Cwd: `room` · Reason: `logout`
   - Transcript: `~/.claude/projects/-home-user-dev-room/2b7b05df-...jsonl`

## Medium value (score 3)

2. **2026-04-06 — Refactoring xray config** (score 3, 42 turns)
   ...
```

## Step 4 — Ask the user which to import

Prompt:

> Import which? (number / numbers / `all` / `none`)

Accept:
- `none` or empty → exit, no changes.
- `all` → queue all pending captures for import in score order.
- `1`, `1,3`, `1-3` → specific selections.

For each chosen capture, hand off to `vault-session-import` with the full
`Transcript:` path from the capture entry. Pass the capture's
`<YYYY-MM-DD>` and `<short-id>` along too — the import skill needs them to
write the `Captured-as:` cross-reference.

## Step 5 — Verify the cross-reference

After each `vault-session-import` invocation completes, re-read `log.md` and
confirm the new `session-import` entry contains:

```
- Captured-as: [<original-date>] session-capture <short-id>
```

If the line is missing, the link from import → capture is broken, and
re-running this skill will show the capture as still pending. Warn the user
and ask if they want you to add the cross-ref manually (single-line append
to the import entry).

## What never to do

- **Do not write to `log.md`.** The log is append-only and only
  `vault-session-import` writes the import entry. This skill is read-only on
  the log.
- **Do not delete capture entries.** Even after import, the capture entry
  stays in the log as the audit trail. The "imported" status is derived
  from the presence of the cross-ref on a later import entry.
- **Do not re-show already-imported captures.** Step 2's filter must run
  before Step 3's display.
- **Do not invent capture entries.** If `log.md` has zero `session-capture`
  entries, say so plainly. Don't suggest the user "should have some" —
  capture happens silently in the background, and a quiet log just means
  the user hasn't run any score-≥-3 sessions yet.
- **Do not score the sessions yourself.** The hook already scored them at
  capture time. The score in the entry is authoritative — don't second-guess
  it.

## Common pitfalls

- **Cross-ref scan misses entries on the same date.** The `Captured-as:`
  line is the only authoritative marker. Don't assume "imported on the
  same day == this capture" — multiple captures can land on one day.
- **Stale transcript paths.** A session JSONL can be moved or deleted
  between capture and review. Before delegating to `vault-session-import`,
  check the path still exists. If it doesn't, tell the user and skip.
- **Wrong vault.** If `$OBSIDIAN_VAULT_PATH` is set in the user's shell but
  this conversation didn't inherit it, you may be reading the wrong log.
  Use `scripts/resolve-vault.sh` from the plugin to get the canonical
  vault path the hook uses.
- **Forgetting older pending captures.** If the user has been ignoring the
  queue for weeks, there may be 50+ entries. Don't drop the ones below the
  display cap silently — surface the count.
