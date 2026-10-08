# Development comparison method

The experiment uses the frozen eligible corpus and Stage 2 configuration revision 2. Retrieval code, models, query preparation and ranking parameters remain unchanged. An external measurement worker wraps the adapters; its hashes and creation time are recorded before the first development query. Additional validators inspect recorded receipts and do not alter retrieval.

Each of the 30 development questions has a disposition for every arm A–F. Runnable pairs receive a fresh process/store search and five searches in the same worker. A retains separate original/fresh index capacity failures. Cold means a fresh process/store: OS caches and the native persistent LLM cache are retained and recorded. The reranking arm may reuse expansions previously cached by the hybrid arm; repeated-query timings do not estimate uncached expansion or reranking cost.

Search receipts separate engine, source-check and mapping time. SQLite's engine interval also includes connection, result mapping and database hashing; QMD reports its own native engine clock. Startup, context reads, sampled memory peaks, admitted budgets and failures are recorded separately. Workers reserve host memory and run within the previously frozen ceilings. Resource refusal and timeout remain comparison outcomes.

Recall and reciprocal rank deduplicate source pages. The original `required_evidence_coverage` metric means that all labeled pages appear in the top ten; it does not establish that passages contain every required fact. Original counts track labeled page/term occurrences; the gate audit additionally requires each term inside its frozen labeled Markdown section and the retained source interval. Both are evidence-location proxies. Neither measure establishes answer correctness.

Diagnostics distinguish missing retrieved pages, wrong source sections and context omissions. All labeled facts must still exist in the eligible frozen corpus. Deeper SQLite ranks are diagnostic observations and do not increase scored recall. Labels may omit other valid supporting pages; demand is derived, engineering-heavy and represented by six development questions per class. Historical/conflicting evidence and multilingual coverage remain sparse.

Questions, source bodies, ranking receipts and diagnostic details stay in the private experiment pack. Held-out questions remain closed until the finalist configuration is locked. Real-wiki answer generation awaits outbound-routing authorization; synthetic trials can prove only their actual client and content path.
