# Retrieval recommendation — research, 2026-10-08

Recommend guarded local SQLite FTS5 search followed by bounded full-page reads as the input to an owner-selected architecture and implementation plan. This is a qualified pilot recommendation: it meets the provisional single-page retrieval and latency targets on this host, but misses the synthesis coverage target and does not prove real-wiki answer usefulness. No production engine, deployment or module layout is approved.

The frozen workload has 755 eligible pages and 40 derived questions (39 English, one Russian), split by topic into 30 development and ten held-out questions. It is engineering-heavy; labels are incomplete and owner priorities remain assumptions. Six development and two held-out questions per class give directional estimates.

| Option | Development Recall@5 / @10 | Warm p95 search with source checks | Cold p95 search, before process startup | Peak sampled worker RSS | Disposition |
| --- | ---: | ---: | ---: | ---: | --- |
| Current full-index read, original/fresh | unmeasured | unmeasured | unmeasured | unmeasured | Both indexes exceed observed 256 KB client read cap |
| SQLite FTS5 | 86.7% / 90.0% | 0.109 s | 0.114 s | 44 MB | Recommend bounded pilot |
| QMD 2.8.3 lexical | 6.7% / 6.7% | 0.104 s | see development receipts | 74 MB | Natural-language AND-query mismatch in frozen adapter |
| QMD vector | 70.0% / 70.0% | 0.148 s | 1.753 s | 672 MB | Synthesis ranking gain; no complete-page coverage gain |
| QMD hybrid, no rerank | 63.3% / 71.7% | 0.649 s | 22.321 s | 3,374 MB | Lower measured overall retrieval; expensive cold path |
| QMD hybrid, rerank | unmeasured | unmeasured | unmeasured | unmeasured | Resource BLOCKED under concurrent host pressure |
| GraphRAG / LightRAG | unmeasured | unmeasured | unmeasured | unmeasured | Desk-study exclusion: missing relationship trigger not met |

Timings include full frozen-source eligibility/hash checks; SQLite engine/open/mapping p95 alone is 0.0116 s. Fresh processes have retained OS/native caches; cold does not mean a flushed machine. Model loading is included in the native cold query; process startup is recorded separately. Resource results describe this CPU Linux workstation, not deployment sizing. See [development results](./development-results.md), private `development-runs.json` (opaque run IDs per arm/query) and `development-summary.json`.

| Development class (six each) | SQLite Recall@5 | QMD vector Recall@5 | SQLite all-required pages @10 | Vector all-required pages @10 |
| --- | ---: | ---: | ---: | ---: |
| Exact | 100% | 83.3% | 6/6 | 5/6 |
| Conceptual | 66.7% | 50% | 4/6 | 3/6 |
| Rationale | 100% | 50% | 6/6 | 3/6 |
| Synthesis | 66.7% | 83.3% | 4/6 | 4/6 |
| Historical | 100% | 83.3% | 6/6 | 5/6 |

SQLite single-page Recall@5 is 22/24 (91.7%), exceeding the 85% target. Synthesis all-required-page coverage is 4/6 (66.7%), below 80%; under the full-page budget only 3/6 synthesis contexts retain every labeled section/term. Vector moves more synthesis pages into the first five, but has equal complete-page coverage and lower recall elsewhere. No ten-point complete-evidence gain or fully resolved priority class was established. Reranking quality is unknown; resource failure is not zero relevance.

The locked SQLite/full-page finalist achieved held-out Recall@5/10 of 95%/100%. All four single-page classes retrieve their two required pages; synthesis Recall@5 is 75% and @10 100%. Nine of ten contexts retain all section/term proxies, including one of two synthesis cases. There is no QMD held-out comparison. Section/term counts describe evidence location, not factual or answer correctness. See [held-out/client results](./heldout-client-results.md), private `holdout-runs.json`, `holdout-classes.json`, `evidence-audit.json` and the immutable `finalist-lock.json`.

The context change has the clearest measured benefit: same 24,000-byte maximum, full-page 25/30 complete location-proxy cases versus passage 10/30. It uses more actual bytes. One-hop links add no complete case; briefings reach 15/30 and require 17,666 upfront bytes plus 6.52 s build/refresh work. Metadata-off rank effects are small and mixed. Graph exclusion is a workload inference, with no graph quality, cost or lifecycle measurement. See [context experiments](./context-results.md).

All guarded B–F adapters passed ten synthetic lifecycle cases in Stage 2, including revocation across search/read/metadata/links and interrupted refresh. Native retained data is distinct from guarded authorization. The actual local MCP SQLite fixture path passed those ten cases plus a date case. Five actual configured-Claude synthetic answer trials cost $0.1236054 total and took 6.78–8.33 seconds each; three complete search/read/citation and two abstain. The date answer includes an unsupported continuity inference and remains PARTIAL. Human interactive use, real-wiki answer quality, other clients/hosts and owner acceptance remain unproved.

SQLite's measured full build takes 0.211 s, produces an 8.44 MB database, and peaks at 53.35 MB. QMD lexical ingestion takes 1.212 s; CPU embedding takes 582.080 s for 1,843 chunks and peaks at 2.268 GB. Its initial database is 18.29 MB, with three downloaded models totaling 2.255 GB. Native cache growth is retained in measurement receipts. These initial-build figures exclude complete production scanning/refresh scheduling and future corpus growth. Private `index-builds.json`, `resource-audit.json`, `model-downloads.json` and lifecycle receipts support them.

Local retrieval has no measured provider charge; compute, electricity, support and future answer usage are unpriced. Expected integration/maintenance effort is lower for lexical search (one derived store, no model lifecycle) than semantic/hybrid or graph retrieval; this is an inference, not an hours estimate. A production eligibility/generation adapter, index refresh, clients, packaging, safe fallbacks and acceptance still require implementation. The recommended pilot cannot be called production-ready from disposable tests.

Sensitivity: if broad synthesis is a hard requirement, no tested configuration qualifies; the smallest next experiment is a separately frozen development set of real owner synthesis questions with semantic fact labels and section-preserving context selection. Do not retune on this opened holdout. If priorities become multilingual recall, the one Russian question is insufficient and a new labeled workload is required. If synthesis ranking alone matters, vector deserves a narrowly scoped follow-up; if reranking matters, repeat a new declared experiment on reserved memory without changing unrelated host processes. Require demonstrated complete evidence improvement within the chosen latency/memory budget before adding a semantic tier. If interactive UX or another host is primary, measure it before selecting placement.

SQLite provides weighted BM25 and explicit query operators; query preparation is part of the tested adapter, so this comparison does not claim that every lexical implementation performs alike. [SQLite FTS5 documentation](https://www.sqlite.org/fts5.html), [pinned QMD source](https://github.com/tobi/qmd/tree/v2.8.3).

Keep derived databases on local storage. Reading source pages from an NFS vault is distinct from placing the SQLite database there; a shared service is a later option that needs its own host and authorization proof. [SQLite network-filesystem guidance](https://www.sqlite.org/useovernet.html).
