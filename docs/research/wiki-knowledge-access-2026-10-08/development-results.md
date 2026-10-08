# Development results — 2026-10-08

All 180 development query/arm pairs have a recorded disposition. Arms B–E completed 720 searches (one cold and five warm per pair). A retains the separate original/fresh capacity failures; F recorded 30 memory-related refusals. No held-out question was opened.

| Arm | Valid pairs | Recall@5 | Recall@10 | All section/term proxies in bounded passage context | Warm p95 incl. source checks | Cold p95 | Sampled engine peak RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 0/30 | unmeasured | unmeasured | unmeasured | unmeasured | unmeasured | unmeasured |
| B | 30/30 | 86.7% | 90.0% | 33.3% | 0.109 s | 0.114 s | 0.04 GB |
| C | 30/30 | 6.7% | 6.7% | 0.0% | 0.104 s | 0.112 s | 0.07 GB |
| D | 30/30 | 70.0% | 70.0% | 0.0% | 0.148 s | 1.753 s | 0.67 GB |
| E | 30/30 | 63.3% | 71.7% | 0.0% | 0.649 s | 22.321 s | 3.37 GB |
| F | 0/30 | unmeasured | unmeasured | unmeasured | unmeasured | unmeasured | unmeasured |

SQLite leads the measured page-retrieval comparison. Its single-page Recall@5 is 91.7% (24 questions), but both labeled pages appear in the top ten for only 4/6 synthesis questions. The original page/term proxy counted 15/30; a corrected section/term audit supports only 10/30 questions. Page retrieval success therefore does not establish sufficient answering context. Wrong section selection and context omissions remain targets for the next task.

QMD lexical AND query preparation is poorly suited to these frozen natural-language questions. Vector and hybrid modes improve on that native lexical behavior but do not outperform the SQLite baseline across this workload. Hybrid cold searches include expansion/model costs; warm searches reuse native caches. No reranking-quality comparison is available: two attempts encountered host-reserve pressure and the remaining attempts lacked admitted headroom. Host process metadata shows substantial concurrent VM/editor memory use and no remaining Node worker after the run. This is a resource-limited observation, not proof that reranking intrinsically exceeds 6 GB.

Source checks, frozen adapter/configuration hashes, all sample metrics/mappings and ten corrupted-evidence controls passed. Diagnosis covers missing pages, section selection and context omissions; deeper SQLite ranks do not change scored recall. Evidence remains derived, incomplete and engineering-heavy. Answer correctness, conflict/date reasoning and real-wiki generation remain unmeasured.

Private evidence: `development-runs.json`, `development-analysis.json`, `development-summary.json`, `development-diagnosis.json`, `measurement-lock.json`, `development-negative.json`, and per-worker logs. No query/source payloads are included here.

Workload fingerprint: `6a3116f73df75f58710b1e9b777282667fb829095a3faeecd0802bc9c0226fb9`.
Configuration fingerprint: `dc4da24b90e05e9ca6515dabc1d4c88424951e92102a84754dae65ba92883fa5`.
Measured-run receipt SHA256: `35281f8c36f372abd16f6f7a39fff315c7569346f88931ecdcd26342fe85f0b3`.

Task 3.2 must evaluate bounded context/link/briefing changes and lock finalists before the held-out/client trials. This development result does not approve a production engine.

Gate audit correction: strict section/term coverage checks the frozen expected section and returned source interval. It establishes evidence location, not semantic fact or answer correctness. Original run counts and fingerprints remain preserved.
