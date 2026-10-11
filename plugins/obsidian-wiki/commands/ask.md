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
Here-string status calls passed the packaged grant in all six latest fake-only
traces. Lookup/citation requests failed their strict schemas, so keep the adapter
unqualified until a fresh authorized run completes lookup, read and verification.

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

### Read request contract

Construct requests from these schemas directly; no documentation/source reader
or shell helper is needed. Send exactly one JSON object per executable call.
Every request includes `schema` and `operation`; unlisted fields refuse. In
particular, `resolve` takes a nested `selector`, never top-level `locator`,
`query`, `generation` or `limit`. Only `get` takes `generation`.

```json
{"schema":"wiki-access.v1","operation":"status"}
```

Exact locator, title and alias use separate selectors. Replace each example
value with the user's exact locator/title/alias; do not send all three for one
lookup. Root-relative locators include `.md`.

```json
{"schema":"wiki-access.v1","operation":"resolve","selector":{"kind":"path","value":"Runbooks/Example.md"}}
```

```json
{"schema":"wiki-access.v1","operation":"resolve","selector":{"kind":"title","value":"Example"}}
```

```json
{"schema":"wiki-access.v1","operation":"resolve","selector":{"kind":"alias","value":"example alias"}}
```

```json
{"schema":"wiki-access.v1","operation":"search","query":"Example","limit":5,"filters":{}}
```

`search` accepts a nonempty query, optional limit 1–10 (use 5), and optional
filters: `category`, `tag`, `evidence_status`, `verification_status`,
`created_from`, `created_to`, `updated_from`, `updated_to`. Date values use
YYYY-MM-DD; unsupported filter availability refuses. Do not add a generation.

For discovery, inspect `ok`, `state`, top-level `generation` and `value.pages`.
Each candidate supplies `page_id` and `locator`. `not_found`/`empty` supplies no
evidence; `ambiguous` needs the user's selection. Copy one to five unique IDs
and their single response generation into the one allowed `get` call:

```json
{"schema":"wiki-access.v1","operation":"get","page_ids":["PAGE_ID_FROM_RESPONSE"],"generation":"GENERATION_FROM_RESPONSE","byte_budget":24000}
```

Inspect `value.pages`, `value.omitted` and `value.read_receipt`. Only returned
complete `pages` are evidence; each has `page_id`, `locator`, `body`, `body_bytes`,
maps and advertised anchors. An all-omitted read has no receipt. Copy the
authentic receipt and each read page's exact ID into citation verification.
Offsets are zero-based UTF-8 bytes within that page's returned `body`, with an
exclusive `end`; `body[start:end]` in UTF-8 must equal the exact quote. They are
not source-file, JSON-serialization or character offsets. Each citation requires
all five fields below, including `page_id`; no `generation` field belongs here.
The example assumes the complete body is `Example.` (eight UTF-8 bytes):

```json
{"schema":"wiki-access.v1","operation":"verify_citations","read_receipt":"READ_RECEIPT_FROM_GET","citations":[{"target":"Runbooks/Example.md","page_id":"PAGE_ID_FROM_RESPONSE","start":0,"end":8,"quote":"Example."}]}
```

Replace all illustrative values with actual returned data, including quote and
offsets; never send placeholder IDs/receipts. Prefer an exact page locator for
`target`; only use an advertised supported anchor when the quote falls inside
it. Repeat a citation record for each displayed occurrence. Before displaying
any answer, require verification `ok:true` and every `value.citations` occurrence
to have `valid`, `target_verified` and `read_verified` all true. Display the
returned verified target. Any request/permission/verification refusal stops;
do not guess another schema or retry in the same answer.

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
