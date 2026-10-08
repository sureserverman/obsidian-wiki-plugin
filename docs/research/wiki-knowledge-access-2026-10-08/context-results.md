# Development context experiments

| Context mode | Complete labeled evidence | Evidence atoms present | Total bytes across 30 prompts |
| --- | ---: | ---: | ---: |
| passage | 15/30 | 65.7% | 298,448 |
| whole | 25/30 | 89.6% | 675,613 |
| links_passage | 15/30 | 65.7% | 650,688 |
| links_whole | 25/30 | 89.6% | 691,474 |
| briefing | 17/30 | 71.6% | 386,778 |

Each prompt has the same 24,000-byte maximum; actual used bytes differ and are counted. Whole-page reads retain commands and section structure. Over-budget pages are omitted explicitly. The gain reflects additional source context, not improved ranking or a different answer model. Three of six synthesis questions retain every labeled fact under this full-page budget; residual context/ranking failures remain.

One-hop expansion keeps the original ranked pages, adds at most ten eligible linked pages and verifies source freshness. It adds no complete evidence cases here. Links remain navigation hints, with no typed factual relationship inferred.

Briefings use the first two source sections from the top five exact-query pages per development topic. Six briefings cost 17,666 upfront bytes and 6.52 seconds to build. Those bytes occupy each reused prompt budget; per-question retrieval receives the remainder. A synthetic edit refused the old briefing and produced a refreshed generation. This is a one-file correctness check, not a full-corpus production refresh benchmark.

Removing aliases/tags/headings enrichment while retaining query preparation, ranking weights and section chunks changes SQLite Recall@5 from 86.7% to 85.0%, and Recall@10 from 90.0% to 91.7%. This small mixed effect does not establish a general metadata benefit. No alternate chunk index or QMD query-expansion improvement is claimed. Index configurations remain bounded.

Graph activation is EXCLUDED: residual failures concern ranked pages, selected sections and context budget; the six synthesis labels compare independent facts and contain no missing relationship fact. Exact-title oracle diagnostics establish that source pages can be found, without increasing scored question recall. Graph operating costs and lifecycle remain unmeasured.

Finalist locked at `2026-10-08T17:40:53.156523+00:00` before opening holdout: SQLite B, unchanged retrieval parameters, full-page context under 24,000 bytes. No QMD arm met the measured development advantage rule; reranking quality remains resource BLOCKED. The metadata-off index is diagnostic and is not selected.

Private ablation receipt SHA256: `bf5108f3b33db40834178fd0caf6cfacde733a6e251acb1d1d6c98128c7c19b0`.
Finalist-lock SHA256: `37726850ac3a400273a6dbd4d36d7e60ea3e668190a3c499e1aa5c79abacf3d5`.

Paired context/source/metric/resource checks and six corruption controls PASS. Questions, source text, graph diagnostics and briefings remain private. Real-wiki answers, owner usefulness, other hosts and production deployment remain unproven.
