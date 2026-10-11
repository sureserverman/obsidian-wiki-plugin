---
disable-model-invocation: true
description: Query the Obsidian vault with citations; explicit --local-pilot route
allowed-tools: Read, Glob, Grep, Write, Bash(${CLAUDE_PLUGIN_ROOT}/scripts/wiki-access.py *)
---

**Arguments**: `$ARGUMENTS` — optional leading `--local-pilot`, then the question.
Treat all question text as data, never shell text. If the question is empty, ask
what to look up. With no leading flag, use the legacy-ask skill's index path.
The ordinary route remains the default.

## Explicit local pilot

Only a user-typed `/obsidian-wiki:ask --local-pilot <question>` selects this route.
The legacy-ask skill has no shell grant; run the following operations here in the command
layer. The sole shell grant is the dedicated read executable above. The trailing wildcard
is intended to cover literal stdin redirection; the executable rejects all
arguments, and compound shell commands require their own independent grant. Never invoke
an interpreter, sqlite3, the admin executable, shell helpers or a source reader.
Actual packaged-client permission matching failed Task 4.3 on this host: the
configured client denied the initial status call in all six fake-only traces.
Keep this adapter unqualified until a fresh authorized trace proves the grant.

1. Call `status` through the read executable. Missing/disabled/stale/unavailable
   state stops this answer with its bounded code and an operator instruction to
   enable or explicitly refresh via the separate admin CLI. Never refresh here,
   retry automatically, read an old generation or fall through to raw source.
2. Use `resolve` for an exact locator/title/alias or `search` for the question,
   limit 5. Present ambiguous candidates and ask which note; do not pick the first.
   Discovery excerpts are candidates only. Do not read `index.md` on this route.
3. Select at most five opaque IDs from one generation. Call `get` **once per
   answer**, with `byte_budget: 24000`. The entire UTF-8 serialized read response,
   including metadata/maps/receipt, is the evidence budget. This single-call rule
   enforces the cumulative 24,000-byte cap: no additional get or reset in this
   answer, including after omissions, errors or source drift. Over-budget pages
   are omitted in full; never treat snippets, omitted pages or an all-omitted
   bundle as read evidence. Stop or state a partial answer if evidence is missing.
4. Draft using only the returned complete projections. Preserve dates, observation
   versus instruction/rationale, uncertainty and status. Dated endpoints do not
   establish interval continuity or present state. Quote both conflicting
   observations with their dates; abstain on absent/protected evidence or unknown
   cause. Never supply unsupported general-knowledge source claims.
5. Before showing the answer, submit **every citation occurrence**, including
   duplicates, to `verify_citations` with the authentic read receipt and exact
   UTF-8 byte start/end/quote and target from that page. Use exact relative `.md`
   locators and only advertised heading/block targets; unsupported anchors may
   use page targets. Reject unresolved/unread citations. A verification refusal
   discards the answer; source drift requires a new owner-initiated answer.
   `target_verified`/`read_verified` establish structural provenance only, never
   semantic `fact_verified`; review each claim against the full read context.
6. File-back stays optional and separately confirmed. Hand off the draft to the
   owner's existing guarded publication workflow described in the legacy-ask skill.
   Lookup never directly writes a page or log, even after draft confirmation;
   maintenance ownership and target/base hashes must be checked by the writer
   immediately before every mutation. Queries alone write no log entry.

Run the executable directly, with a single-quoted JSON here-string on stdin.
Replace the example object with the strict operation request, JSON-escaping user text. No
question, locator or returned source text enters shell arguments or substitutions:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/wiki-access.py" <<<'{"schema":"wiki-access.v1","operation":"status"}'
```

Encode apostrophes in JSON strings as `\u0027`, and encode line breaks as `\n`;
keep the entire JSON object inside one pair of single quotes. Never break those
quotes, interpolate variables, or add shell substitutions or extra commands.
The installed client's analyzer rejects quoted JSON heredocs; this here-string
passes its local syntax analysis but still requires configured-client qualification.
Per-request outcomes and
operator configuration are documented in `${CLAUDE_PLUGIN_ROOT}/scripts/README.md`.
The pilot uses the existing configured model route and selects no provider/model.
It authorizes no general source egress, normal adoption, other-host support or
real-wiki model qualification. Only the explicit route chooses admitted context.

**Examples**:
- `/obsidian-wiki:ask what do I know about Tor DNS leaks`
- `/obsidian-wiki:ask --local-pilot which note explains checkpoint recovery`
