---
name: vault-query
description: >
  Use when the user asks a research or recall question that their Obsidian vault at
  ~/dev/knowledge might answer, or mentions "/obsidian-wiki:ask". Trigger on "what do I know about X",
  "what's in my notes about Y", "check my wiki for Z", or any factual question in a domain
  the vault covers (Tor, DNS, Android, Matrix, packaging, fingerprinting, etc.).
---

# Vault Query

Answer a question against the Obsidian vault at `~/dev/knowledge`, citing every claim,
and optionally filing the answer back as a new wiki page if it has lasting value.

The vault has an existing hand-curated index at `Home.md`. Always use it as the search
entry point before falling back to grep.

## Step 1 — Scan `Home.md`

Read `~/dev/knowledge/Home.md` first. It is a Map-of-Content containing tables organized
by category (Infrastructure, Android, Browser Extensions, Installers, Security,
Desktop Tools, Router Firmware, AI Tooling, Technology Index, Patterns Index, Gotchas
Index, Architecture Index, Platform Index).

Treat the links in these tables as a retrieval index. For the user's question, skim the
tables and list the 3–8 pages most likely to contain relevant material. Do not read
every page the index mentions — just the plausible matches.

If `Home.md` does not exist or is empty, the vault may not be fully bootstrapped. In
that case, fall back to `ls` of the six category directories plus grep for keywords —
but tell the user the index is missing.

## Step 2 — Targeted reads

Read each of the pages identified in Step 1 in full. These pages are small (usually
under 200 lines) — read them end-to-end rather than grepping inside them. You need the
context.

Do **not** read every page in a category just because the category name sounds
relevant. Only read pages that `Home.md` specifically identified.

If after reading the identified pages you still don't have an answer, expand the
search: grep the six category directories for specific terms from the question, then
read any new hits. Note in your answer that you had to go outside the index.

## Step 3 — Synthesis with citations

Write the answer. Every factual claim cites its source as an Obsidian wikilink:

> VLESS/REALITY requires a valid TLS handshake upstream for SNI forwarding
> ([[Xray-VLESS]]), and bridges must be used because Tor cannot bootstrap through an
> Xray transparent proxy ([[Tor Bootstrap Through VLESS]]).

Rules:

- **Every claim is cited.** If you can't cite it, you can't include it.
- **Cite the specific page**, not the category.
- **If a claim came from a `raw/` source** (an article that was ingested), cite both
  the wiki page and the original file: `([[DNS Leaks]], raw/dns-leak-research.md)`.
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

When the user agrees:

1. Pick the category (usually `Gotchas/` or `Patterns/` for synthesized answers).
2. Write the page using the schema from `CLAUDE.md` (same frontmatter as `vault-ingest`
   would use).
3. Cite every wiki page that fed into the synthesis.
4. If the answer was derived from a concrete question, record the question in the
   page's body so future-you has context for why it exists.

## Step 6 — Log the activity

If and only if a page was filed back, append a log entry:

```
## [YYYY-MM-DD] query | <topic>
- Question: <one-line summary of the question>
- Filed: [[New Page]]
- Sources: [[Page A]], [[Page B]]
```

Queries that do not produce a new page do **not** get logged — the log would become
noise.

## Common pitfalls

- **Answering without reading `Home.md` first.** The index is curated; using grep as
  the primary retrieval tool wastes context and misses the user's organization.
- **Reading the whole vault.** Targeted reads only.
- **Fabricating citations.** Every `[[link]]` in your answer must resolve to a real
  file.
- **Silently choosing between contradictory pages.** Surface it.
- **Filing a new page without asking.** Always confirm.
- **Filling gaps with general knowledge without flagging.** If the vault doesn't know,
  say so.
