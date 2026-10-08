# Held-out and actual-client findings

The finalist lock preceded the held-out opening. One pass evaluated ten held-out questions with SQLite B and full-page context; no ranking, prompt, model, context or label tuning followed. The full matrix retains 240 development/held-out pair dispositions. QMD modes were excluded from holdout because they were not locked finalists; this is not a measured QMD holdout comparison.

| Held-out class | Questions | Recall@5 | Recall@10 | Complete labeled context |
| --- | ---: | ---: | ---: | ---: |
| exact | 2 | 100.0% | 100.0% | 2/2 |
| conceptual | 2 | 100.0% | 100.0% | 2/2 |
| rationale | 2 | 100.0% | 100.0% | 2/2 |
| synthesis | 2 | 75.0% | 100.0% | 1/2 |
| historical | 2 | 100.0% | 100.0% | 2/2 |

Overall held-out Recall@5 is 95%, Recall@10 is 100%, and complete labeled context is 9/10. Warm search p95 is 0.108 seconds including source checks over 50 repetitions. Two questions per class make these directional findings. Multi-page context still fails one question despite retrieving every required page. The larger development comparison remains the selection evidence.

The existing Claude Code 2.1.294 / configured claude-opus-5-5 client completed five bounded synthetic-only trials through an isolated stdio MCP adapter over guarded SQLite. Available tools were exactly search, get and status; built-in tools, hooks and unrelated MCP configuration were disabled per process. No global configuration changed, and no real-wiki body was served. Ten fixed synthetic cases plus one date fixture passed actual local MCP search/read checks, including absent knowledge, protected content, instruction-as-data and lifecycle refusal.

Actual answer-client cost totaled $0.124; individual trials took 6.78–8.33 seconds. The actual client searched and read sources before producing cited answers. It abstained on absent/protected evidence, ignored the injected instruction, and returned zero fabricated citation targets or seeded protected canaries. These trials prove the tested synthetic CLI path; they do not establish real-wiki answer quality, human interactive usefulness or other hosts.

The date trial retrieved both historical/current pages and cited their dated values correctly. Its additional uninterrupted-interval narrative is not supported by two dated observations. This answer-support defect is retained in the private review; no prompt retry or tuning erased it. A later implementation must constrain historical inference and validate that boundary.

The original harness is archived and hashed. Only validation/reproduction functions changed to reconcile complete receipts and require a held-out query to bind to its actual authorized client trace. An AST comparison verifies that retrieval functions, constants and other statements remain identical. The original configuration/workload fingerprints remain in force. A separate synthetic cited-answer receipt cannot satisfy a real-wiki held-out cited-answer reproduction gate.

Protocol reference: [official MCP server guide](https://modelcontextprotocol.io/docs/2026-07-28/develop/build-server). Runtime evidence uses the already installed official server SDK 2.0.0; private raw client/server receipts, costs, tool sequences and source checks are retained.

Task 3.3 command check PASS: 40 questions, 240 pair dispositions, five actual synthetic answer-client trials, ten fixed MCP cases and one date case. Stage 3 independent judgment is still required. Real-wiki answer generation and the later held-out cited-answer trace remain BLOCKED pending outbound authorization; owner usefulness remains ACTION NEEDED.

Finalist-lock SHA256: `37726850ac3a400273a6dbd4d36d7e60ea3e668190a3c499e1aa5c79abacf3d5`.
Combined run receipt SHA256: `2bdd2981bf446593c259165cca6ca8a1fba765d01da85e2b3b68742ea5c83e09`.
