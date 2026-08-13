# Security Review — obsidian-wiki-plugin

**Date:** 2026-08-13T16:23:44Z
**Scope:** whole repo at `0174e5f` (both plugins: `obsidian-wiki`, `vault-context`)
**Result:** 1 HIGH found and fixed, 1 LOW found and fixed, 2 LOW open, 3 INFO

## Provenance — read this before trusting the tally

**This is a manual review, not a `/sec-audit` pipeline run.** The `sec-audit`
plugin is installed and enabled on this host, but it was not available as an
invocable skill in the session that produced this file, so its four-agent
pipeline and live CVE enrichment (NVD 2.0, OSV.dev, GHSA, CISA KEV) **did not
run**. This file is deliberately *not* named `sec-audit-report-*.md`: the
portfolio's `global-security.md` dashboard consumes those, and a hand-written
file in that slot would misreport a pipeline run that never happened.

To close the maturity axis canonically, run `/sec-audit` in this repo. Findings
below should survive that run; treat them as a head start, not a substitute.

**Lanes that ran:** shellcheck (all 24 shell scripts), bandit (recursive over
`plugins/`), ruff, manual source review of the hook and parsing surface,
targeted proof-of-concept exploitation, secrets grep, permission sweep.
**Lanes that did not run:** semgrep (binary present but reports no version —
not exercised rather than reported clean), dependency CVE enrichment (no
third-party dependencies — both plugins are bash + stdlib Python), trivy,
grype, gitleaks (absent from PATH).

---

## HIGH

### H-1 — Command injection via `cwd` in the SessionEnd hook (CWE-78) — FIXED

`capture-session.sh` built its detached background script by interpolating hook
values into the script text:

```bash
nohup bash -c '
    SESSION_ID="'"$session_id"'"
    CWD_VAL="'"$cwd_val"'"
    …
'
```

Each value landed inside a **double-quoted assignment in the generated script**.
Command substitution is performed inside double quotes, so a `$(...)` or a
backtick anywhere in a value was executed by the background shell. No quote
character was needed to escape — the substitution ran on its own.

**Reachability.** `cwd` is the directory the user ran Claude Code in, taken from
the SessionEnd hook payload. Directory names may legally contain `$( )` and
backticks on Linux and macOS. An attacker who controls a directory name the
victim will work in — a repo, tarball or zip that unpacks to a crafted directory
— gets arbitrary code execution as the victim, triggered by *ending one session*
in that directory. No further interaction, and the hook is fire-and-forget, so
nothing is displayed when it fires. `transcript_path`, `session_id` and the
vault path are injectable by the same mechanism but are far less
attacker-reachable.

**Confirmed by proof-of-concept**, not by inspection: a payload of
`/tmp/proj$(touch <marker>)` in `cwd`, with an otherwise ordinary transcript and
vault, created the marker file. Re-run after the fix, the marker is not created,
the value is recorded verbatim as data, and a normal capture still succeeds.

**Fix:** values are passed as positional arguments (`bash -c '…' _ "$session_id"
…`) and read as `"$1"`, `"$2"`, …. Nothing is interpolated into script text.

**Regression test:** `tests/test_capture_session_injection.sh` — asserts the
payload does not execute, that `$( )` and backticks are both inert, that the
value survives as literal data, and that a normal capture still works (a script
that merely fails to parse would otherwise "pass"). Mutation-probed: restoring
the interpolation makes the test fail.

> Caution for future edits: the background block is a single-quoted string.
> An apostrophe in a comment inside it terminates the string — this happened
> while writing the fix and was caught only by running the hook. Both blocks
> now carry a note.

---

## LOW

### L-1 — Same interpolation pattern in `check-update.sh` — FIXED

`CACHE_FILE` and `MARKETPLACE_DIR` were baked into a background block the same
way. Both are plugin-controlled paths (`/tmp/claude/…` and the marketplace clone
under `$HOME`), so there is no realistic attacker path — but the pattern is
identical and was fixed identically.

### L-2 — Predictable shared cache path `/tmp/claude` — OPEN

`check-update.sh` writes, and `statusline-snippet.sh` reads,
`/tmp/claude/obsidian-wiki-update-check.json` at a fixed path in a world-writable
directory. On a multi-user host another user can pre-create `/tmp/claude` (or the
cache file) and control the contents the plugin later reads, or point it
elsewhere by symlink. Impact is limited: the cache holds git SHAs and a boolean,
and the worst outcome is a false or suppressed "update available" nudge.

Not fixed here — `/tmp/claude` appears to be a convention shared with other
tooling on this host, so relocating it unilaterally (e.g. to
`${XDG_RUNTIME_DIR:-$XDG_CACHE_HOME}/obsidian-wiki/`) is a cross-project decision
rather than a defect fix. Recommend deciding it portfolio-wide.

### L-3 — Untrusted transcript text reaches the model's context — OPEN

`score-session.py` extracts `topic` from the **first user message of an
arbitrary session transcript**. It flows into `<vault>/log.md` and into the
auto-import queue job, and `drain-queue.sh` prints it into the SessionStart
`additionalContext` block that the model reads:

```
- session=%s score=%s topic=%s transcript=%s
```

A session transcript containing instruction-shaped text therefore reaches a
later agent's context. This is a prompt-injection channel, not a code-execution
one. Existing mitigations are real but incidental rather than deliberate:
whitespace is collapsed to a single line, `|` is replaced with `/`, and the
string is truncated to 60 characters — which bounds an injection to a short,
newline-free fragment inside a labelled field.

Worth an explicit decision: either document the 60-char truncation as a security
control so it is not "optimized" away later, or delimit the field so injected
text cannot be mistaken for a directive. Same consideration applies to the
Cursor/Codex/Gemini/OpenCode transcripts the scan skills read, which are equally
untrusted.

---

## INFO

### I-1 — shellcheck: 0 errors, 8 warnings, 15 notes

No security-relevant results. Notably `SC2088` ("Tilde does not expand in
quotes") fires twice in each `resolve-vault.sh` — both are **false positives**:
the hits are the `case` patterns `"~"` and `"~/"*` inside `expand_tilde()`,
whose entire purpose is to match a literal tilde before expanding it. `SC1083`
in `check-update.sh:80` is likewise a false positive on git's `@{upstream}`
syntax. The `SC1091` notes are unfollowed `source` lines for sibling libraries.

### I-2 — bandit clean; ruff 15 style findings, none security

Ruff reports timezone-naive datetimes (`DTZ011/DTZ012`), `SIM115` file handles
outside context managers in `build-index.py`, and one blind `except Exception`
in `score-session.py:85` — which is deliberate there (a parse failure must
degrade to "skip this line", never crash a hook).

### I-3 — no secrets, no world-writable or setuid files

Grep for credential-shaped assignments returns nothing; no tracked file is
group/other-writable or setuid. No third-party runtime dependencies exist in
either plugin, so there is no dependency CVE surface to enrich.

---

## Review metadata

| | |
|---|---|
| Commit reviewed | `0174e5f` |
| Shell scripts | 24 (shellcheck: 0 error, 8 warning, 15 note) |
| Python modules | 4 (bandit: 0 findings; ruff: 15 style) |
| Third-party deps | none |
| Tests before | 17 |
| Tests after | 18 (+ injection regression) |
| PoC performed | yes — H-1 confirmed exploitable pre-fix, blocked post-fix |
