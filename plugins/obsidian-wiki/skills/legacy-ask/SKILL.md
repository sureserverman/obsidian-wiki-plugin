---
name: legacy-ask
allowed-tools: Read, Glob, Grep, Write
description: >
  Use when the user asks a research or recall question that their Obsidian vault at
  <vault> might answer, or mentions "/obsidian-wiki:ask". Trigger on "what do I know about X",
  "what's in my notes about Y", "check my wiki for Z", or any factual question about tools,
  protocols, decisions, or gotchas the user has written up in their notes.
---

> **Vault path:** `<vault>` is published by the SessionStart hook at
> `${XDG_CONFIG_HOME:-~/.config}/obsidian-wiki/state/vault-path` — **Read** that file;
> do not shell out. If it is missing (hooks disabled, or a first session before the
> hook has run), read `default_vault` from `~/.config/obsidian-wiki/config.json`, and
> fall back to `~/dev/knowledge`. The hook is the only place `$OBSIDIAN_VAULT_PATH` is
> honoured, so reading its output keeps skills and hooks pointed at the same vault.

# Vault Query

Answer a question against the Obsidian vault at `<vault>`, citing every claim,
and optionally filing the answer back as a new wiki page if it has lasting value.

An explicit user-typed `ask --local-pilot` is executed by the command layer's
separate guarded JSON read CLI workflow. This skill acquires no Bash grant and
never invokes that route from natural-language triggers. Ordinary ask retains the
legacy path below. The pilot bypasses the index and uses one bounded full-note get,
authentic receipts and verification of every citation occurrence before display.
Refusal never becomes a direct-source fallback. File-back remains separately
confirmed under the existing maintenance/publication gates.

The vault has an auto-generated retrieval index at `index.md`. Always use it as the
search entry point before falling back to the legacy `Home.md` Map-of-Content or grep.

## Step 1 — Scan `index.md`

Read `<vault>/index.md` first, subject to the client's whole-file read limit
(256 KiB on the measured host). An oversized index is unsupported for this legacy
route: report that limit and offer the explicit opt-in local pilot or an
owner-selected guarded bounded lookup. Do not bypass policy with arbitrary source
reads or treat a partial index as complete. It is the current generated inventory of published
pages, grouped by category with paths, summaries, tags, aliases, topics, and evidence
metadata. It excludes protected records and raw/private paths.

Treat the links in these tables as a retrieval index. For the user's question, skim the
tables and list the 3–8 pages most likely to contain relevant material. Do not read
every page the index mentions — just the plausible matches.

If `index.md` does not exist or is empty, fall back to `Home.md` if it exists. If
neither index exists, the vault may not be fully bootstrapped: fall back to `ls` of the
category directories named in the vault's `CLAUDE.md` plus grep for keywords — but tell
the user the generated index is missing.

## Step 2 — Targeted reads

Read each of the pages identified in Step 1 in full. These pages are small (usually
under 200 lines) — read them end-to-end rather than grepping inside them. You need the
context.

Do **not** read every page in a category just because the category name sounds
relevant. Only read pages that the retrieval index specifically identified.

If after reading the identified pages you still don't have an answer, expand the
search: grep the category directories named in the vault's `CLAUDE.md` for specific terms from the question, then
read any new hits. Note in your answer that you had to go outside the index.

## Step 3 — Synthesis with citations

Write the answer. Every factual claim cites its source as an Obsidian wikilink:

> WireGuard needs each peer's public key on both ends
> ([[WireGuard Peer Keys]]), and a relay must be used because the tunnel cannot start behind a
> captive portal ([[Tunnels Behind Captive Portals]]).

Rules:

- **Every claim is cited.** If you can't cite it, you can't include it.
- **Cite the specific page**, not the category.
- **Chat-derived claims use safe evidence anchors only.** Cite the published page
  and its opaque event anchor. Never expose a `raw/` path, protected locator, or
  participant identity; protected originals need an explicit authorized route.
- **Prefer quoting** for surprising or technical claims — paraphrasing loses nuance.
- **If the vault doesn't answer the question**, say so explicitly. Do not fill in from
  general knowledge without flagging it.

## Step 4 — Surface contradictions

If two pages in the vault make conflicting claims about the same thing, do **not**
silently pick one. In the answer, quote both, cite both, and tell the user they
contradict. This is one of the most valuable things the wiki layer can surface — hiding
it defeats the purpose.

Example:

> [[Nym Mixnet Evaluation]] considers Nym "too immature (Jan 2026)" but
> [[Full Privacy Chain]] lists a Nym layer in the recommended stack. These disagree —
> the evaluation page is newer, so the chain page may be stale.

## Step 5 — Offer to file back (optional)

If the answer has lasting value — a new Gotcha, a new Pattern, a cross-domain insight
that didn't exist on any single page — offer to save it as a new wiki page. **Ask
first.** Do not file unprompted.

When the user agrees, prepare the proposed page content and destination for the
owner's existing guarded writer workflow. Include category/schema, each source
citation and the original question. Agreement to a lookup or a draft does not
permit direct Write or a log mutation from ask.

The separate publication operation must follow WF-VAULT-WRITE-MAINTENANCE (and
WF-CHAT-PUBLISH for a chat-derived batch): owner confirms exclusive maintenance,
the writer checks current ownership/expiry immediately before **every mutation**,
then rechecks affected target/base hashes. A foreign, malformed or expired window,
missing capability or changed base hash blocks the write. Keep capability tokens
out of drafts, answers and logs. Do not grant admin, interpreter or generic shell
access to lookup to perform this handoff. The operator runs the existing guarded
publication workflow; ask remains read-only even after draft confirmation.

## Step 6 — Log only a completed publication

Only the separate guarded writer appends the query log entry, after the confirmed
page was actually filed. It applies the same maintenance and base-hash checks to
`log.md`. A lookup, accepted draft, failed or blocked publication creates no query
log. The entry records the question, filed page and source citations.

## Common pitfalls

- **Answering without reading `index.md` first.** The index is curated; using grep as
  the primary retrieval tool wastes context and misses the user's organization.
- **Reading the whole vault.** Targeted reads only.
- **Fabricating citations.** Every `[[link]]` in your answer must resolve to a real
  file.
- **Silently choosing between contradictory pages.** Surface it.
- **Filing a new page without asking.** Always confirm.
- **Filling gaps with general knowledge without flagging.** If the vault doesn't know,
  say so.
