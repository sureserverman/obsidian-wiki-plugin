# Stage 2 gate — PASS, 2026-10-09

Scope: `703748b..ab31956`, followed by the SQLite construction fix in this gate
commit. Selected canonical plan: `2026-10-09-local-sqlite-wiki-pilot-plan.md`,
Tasks 2.1–2.3. Review scope: standard. All implementation tasks declared inline.

The store indexes admitted projections as section rows with exact UTF-8 mappings,
the frozen research stopwords and weighted quoted-OR BM25 (5/3/2/1/1). Natural
query parsing preserves command switches and slash/colon tokens; ATX section
parsing ignores fenced headings. These declared parser differences need fresh
acceptance; no historical recall result is promoted to this implementation.

Generations bind source-root identity, complete potentially eligible membership,
source/projection hashes, policy and schema/recipe versions. Reads pin one local
generation. Resolve/search/status guard both before use and before returning
buffered results. Empty results require verified freshness. Metadata, response
budgets, filters and ambiguity use explicit outcomes. Discovery supplies no read
receipt; Stage 3 evidence/CLI operations remain unavailable.

Private first writes, mount/device checks, descriptor-relative publication and
reclamation, directory/file durability, reader pins and writer locking qualify the
local lifecycle on fake fixtures. Remaining store capacity constrains SQLite
construction after manifest/pointer reservation. Owned failed staging is removed;
pinned old generations survive only physically and cannot serve revoked content.
NFS hashes establish observations on this host, never an instantaneous distributed
snapshot or revocation of bytes already delivered.

Evidence: host Python/SQLite, fake local temporary vaults only.

- `python3 tests/wiki_access_cases.py Stage2IntegrationCases`: 3/3 PASS.
- Final `bash tests/run.sh`: 40/40 wrappers PASS, 16.020 seconds; pilot unit
  wrapper runs 40 cases, integration wrapper runs four cases across Stages 1–2.
- Fix scope: Store 6 + Generation 10 + Lookup 3 + Stage2Integration 3 = 22/22 PASS.
- Stage-order check, gate/dispatch static validators and `git diff --check`: PASS.
- Private regression log and timed receipt remain in the ignored private pack.

review: Tier-1 independent default `/root/store_review` over Task 2.1 — 0 Critical,
3 Important, repaired with strict schema/record refusal and concrete ranking,
map, SQL execution and runtime tests.

review: Tier-1 independent default `/root/generation_review` over Task 2.2 —
filesystem/inventory/manifest/lock/mount/FIFO classes repaired; source-write class
independently confirmed corrected. Final Important remaining-capacity finding
fixed with a direct persistent-storage-budget control. No unreviewed Critical remains.

review: Tier-2 independent default `/root/stage2_review` over `703748b..ab31956` —
1 Critical, 0 Important, 0 Suggestions. Gate remediation round 1 of 2 fixes the
SQLite leaf-reopen race: in-memory construction serializes through the original
safe-created descriptor, with live leaf/inode/link validation. Independent
Critical fix-scope re-review PASS (21 cases at its receipt); actual Manager
hardlink and symlink injections refuse with fake sources unchanged. The additional
whole-source-preservation control also passes in the executor's 22-case receipt.
In-memory construction closes its connection explicitly; actual corpus RSS and
latency qualification remain due in Stage 4.

Defect-class sweep:
`rg -n 'os\.(open|mkdir|replace|unlink|rmdir)|write_private|snapshot' plugins/obsidian-wiki/scripts/wiki_access/generation.py`
and all SQLite connection/construction sites in `wiki_access/store.py`.
Every mutation of derived state binds an open parent or leaf descriptor. No
source-write capability or maintenance lock is acquired by retrieval.

dispatch: 0 of 0 rostered worker tasks dispatched; 3 declared-inline tasks,
confirmed by Executor trailers on `ac421b0`, `65781ec`, `ab31956`.
The prior documentation-only handoff commit carries no task trailer.
ledger: NOT RUN — no dispatch log; actual review tool results are the evidence.
evaluator: not required — this stage has no judgment gate.
platform verifier: no matching Python platform hook; explicit gate commands ran.

Residuals: Stage 3 bounded reads, signed receipts, citations and CLI unimplemented;
Stage 4 configured-client, fresh independent acceptance, real-vault performance
and owner usefulness unproved. Development fixtures only; private acceptance
manifests and historical research artifacts were not opened for retrieval or
tuning. Pilot/client activation and broader source egress remain unselected.
DEC-001/002/003 and GDEC-SEC-001 retain their existing boundaries.
