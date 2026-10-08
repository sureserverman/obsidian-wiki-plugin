# Solution-shaping brief — proposal, 2026-10-08

This brief supplies inputs to an owner-selected architecture and a later implementation plan. The measured candidate is local SQLite FTS5 plus bounded full-page reads; no module tree, service, production MCP entry, UI or binding engine decision is approved. [Recommendation and limitations](./recommendation.md).

## Proposed access experience and contract

Start with question → ranked eligible pages → explicit reads → supported citations. Agents should use bounded search rather than requiring one complete `index.md` read. Interactive users should be able to inspect ranked titles, dates and source sections before requesting an answer. The latter is a proposed experience with no human UX trial. Keep lookup useful without an answer-model call.

A proposed versioned API has `search(query, limit, filters)`, `get(page_id, generation, byte_budget)` and `status()`. Return bounded ranked page IDs, safe published locators/anchors, source dates, matched section spans, generation and omission/truncation flags. Distinguish empty eligible results, unsupported query/filter/schema, unavailable index, drifted generation, permission refusal and budget exhaustion. This explicit contract is informed by disposable CLI/MCP receipts; exact schema and compatibility need architecture selection and integration tests.

Use opaque IDs mapped only to eligible published pages. A citation must resolve to the generation actually read; source snippets alone are insufficient proof of a complete answer. For short pages prefer full reads within the measured 24,000-byte maximum. Explicitly omit over-budget pages and state missing evidence. Section-preserving targeted reads are a follow-up hypothesis for long notes, not an evaluated production solution. Avoid inferring that literal section/term matches establish a fact.

Answers should abstain on absent support, cite each source-backed claim, and preserve observed/proposed/failed/contradicted and historical/current distinctions. Present conflicting dated evidence without upgrading two observations into a continuous interval. Existing `ask` already requires citations and surfacing contradictions. Synthetic Claude trials demonstrate a constrained search/read/citation route, while the date case shows a remaining unsupported inference; production answer support remains a validation gap.

## Eligibility, freshness and revocation

Propose one authorization policy applied before indexing, search snippets, reads, metadata and link expansion. Include only explicitly allowed published categories and record shapes; exclude ambiguous sensitivity, protected markers, raw/original/identity/draft paths, and symlinks escaping approved roots. Follow no provenance link into source archives. Portfolio integrations require their own explicit allowlist rather than treating every Portfolio document as eligible. Compatibility with current publication policy must be checked in implementation.

The measured guard rechecks source hashes and refuses drifted generations. Production should preserve this fail-closed behavior across add/edit/delete/rename/reclassification and interrupted refresh. An old ID or cached context must not expose removed/protected content. Every derived surface, database/cache, briefing and retained generation needs a revocation/retention policy. Guarded denial differs from physical native-store erasure; the research lifecycle receipts document that distinction. Full-corpus checks currently dominate ordinary search time; reducing that cost requires measured freshness correctness under races, not merely a faster timestamp check.

Source pages remain authoritative and read-only to retrieval. A refresh should build a new local derived generation and expose it only after validation; atomic local-generation switching and concurrent-read behavior are proposed and untested at production scale. Source publication must retain DEC-003's owner-confirmed exclusive maintenance and base-hash checks on the shared NFS vault. Retrieval does not grant publication permission.

## Placement, languages and model policy

Prefer a local derived database on the measured workstation for the first architecture candidate. Read the shared vault as source; avoid putting SQLite on NFS. A service hosted next to local storage is an alternative for shared clients, with authorization, deployment, contention and failure behavior to be proven. Only CPU Linux performance was measured; Pi/macOS/mobile and GPU sizing are BLOCKED without a named target. [SQLite guidance](https://www.sqlite.org/useovernet.html).

Keep exact commands, aliases and source languages in query preparation and citations. The workload has 39 English questions and one Russian question, so multilingual quality is insufficiently tested. Do not introduce automatic translation or query expansion as an assumed improvement. A future language-specific workload must be independently frozen.

Retrieval/embeddings stay local by default. The pilot recommendation needs no embedding or reranking model. Use the existing client's configured answer-model route if authorized; do not silently select a provider or build a direct provider client. Published source content is not automatically cleared for remote processing. Real-wiki generation and the held-out client binding remain BLOCKED pending an explicit content-routing choice; synthetic trials alone demonstrate transport. MCP is a possible adapter protocol over the selected backend, with per-client tool authorization and bounds; it does not establish quality. [MCP architecture](https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture).

## Project context, migration and affected consumers

Preserve DEC-001 containment eligibility in `plugins/vault-context/scripts/lib/eligibility.sh`, including write, validation and SessionStart callers. Search scope may use the eligible project's signals; no new registration requirement or grouping-folder sidecar is proposed. Keep the matcher's current Portfolio self-integration guarantee explicit. Briefings remain optional: measured upfront context and refresh costs gave no advantage over bounded full-page reads.

A later implementation should inspect these concrete surfaces:

| Consumer or contract | Proposed impact | Evidence or remaining validation |
| --- | --- | --- |
| `plugins/obsidian-wiki/skills/ask/SKILL.md`, `commands/ask.md` | Replace mandatory full-index scan with bounded search/read while preserving citation, contradictions and owner-approved file-back | Read-cap failure and retrieval receipts; actual skill integration untested |
| `plugins/obsidian-wiki/scripts/build-index.py` | Share an explicit eligible projection/generation policy, retaining readable index for existing consumers | Source exclusions need consistency; no production builder change made |
| `plugins/vault-context/scripts/match-index.py`, `render-matches.py`, `write-context.sh`, `session-start.sh` | Evaluate bounded project recall, safe citations, refresh/invalidation, and self-integration | Current overlap/recency path inspected; project-agent acceptance untested |
| `plugins/vault-context/skills/link/SKILL.md`, commands and template | Describe status and stale/unavailable behavior without duplicating large context per session | Proposed migration; existing containment remains binding |
| `ports/cursor/obsidian-wiki/skills/wiki-ask/SKILL.md`, copied scripts, agents and installer | Preserve the manual port contract and script parity with explicit host-specific prose | Cursor runtime untested; install/permission/tool availability need evidence |
| `docs/workflows/WF-CHAT-IMPORT.md`, `WF-CHAT-PUBLISH.md`, `WF-VAULT-WRITE-MAINTENANCE.md` | Preserve reviewed-publication, protected-source, safe-anchor and maintenance behavior | Existing contracts remain unchanged |
| Candidate query workflow/spec and tests | Define bounded search/read/cite/abstain, stale refusal, long-page handling, dates and supported client paths | No new WF-ID allocated or workflow adopted by this research |

On missing/corrupt/stale index, return an explicit unavailable state. Offer a bounded scan/read of user-selected eligible published files or a verified fresh local rebuild; this is a proposed fallback with no production proof. Never present stale cache as fresh evidence or route around protected-content denial. Retain the existing full-index path only where it fits the actual read cap and is explicitly supported. Migration/rollback should be feature-gated in a later plan, preserving existing commands and making failure visible; this proposal is not activation.

## Architecture and implementation handoff

The later ARCH proposal should contain purpose/non-goals and actual workloads; eligible source and privacy boundaries; versioned query/read/citation/error contracts; generation/revocation/cache retention; local versus service topology and host requirements; client adapters and permissions; language/model routing; project context containment/self-integration; safe fallback; migration/rollback; observability without payload logs; acceptance and operational ownership. Module layout belongs to that architecture decision.

Record binding DEC entries only after owner selection of backend, placement, content route, cache retention, supported clients and acceptance thresholds. Preserve DEC-001/002/003 and GDEC-SEC-001; any change to their constraints requires explicit supersession. Raw security findings remain local; sanitized constraints alone enter canonical documents. The proposed behavior contracts and architecture need review before production tasks are authored.

Remaining decisions are actual owner questions/priorities, interactive experience, outbound policy, supported hosts/clients, private retention and whether synthesis is a hard target. Next validation should use fresh development questions, semantic support labels and owner usefulness grading. The scoped final trace uses one already frozen held-out query without tuning, only after its content route is authorized. No further answer prompt/model changes are authorized by this research.
