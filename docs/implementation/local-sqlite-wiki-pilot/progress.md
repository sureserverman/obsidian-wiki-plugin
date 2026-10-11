# Local SQLite wiki pilot execution

Selected by the owner's “execute the plan” instruction on 2026-10-09.
Canonical plan: `/mnt/vault/Portfolio/ai-tools/obsidian-wiki-plugin/plans/2026-10-09-local-sqlite-wiki-pilot-plan.md`.
Approved plan SHA256: `ac41bf26d9df281c3d2903adf278b6324724d789b27bba1b8a9e7473664ad3f5`.
Approved architecture SHA256: `27c2eaa174e20e8616e637ba1c21931cb7ab8bc43cfc4ad5caf2e32c2aa436e4`.
Base: `d2633309916c5fdf9308831d1a9468a5a54f28d8`; clean initial tree; branch `feat/local-sqlite-wiki-pilot`.

Preflight: 38/38 existing regressions passed; Python 3.12.3, SQLite 3.45.1, in-memory FTS5 probe passed. Source resolver returns `/mnt/vault` on NFS4; private development/acceptance directory created 0700 on local ext4 outside Git/vault. No source writer needed. Four existing decisions remain in force. Static plan validators: ten gate checks, nine executable/one judgment; all fourteen tasks inline. Review scope remains standard with required per-task reviews on named boundaries. Actual independent reviewer agents are available; no inline review substitution required. New test families are created by their specified tasks; none exists or has passed yet. Selected retention: active plus staging and pinned old generations, 128 MiB store cap; 256 MiB worker budget, 24,000-byte evidence cap. No real-source model authorization; fake-only six-trace allowance comes from the selected plan.

Status: preflight complete; Task 1.1 next. Core, packaged-client integration, real-vault lookup and owner usefulness remain unproved. Private execution path is in ignored `.claude/plan-progress.json`.

Task 1.1 PASS at 0f7a6a5 (three contract checks, missing-family negative control).
Task 1.2 PASS: ContractCases+PolicyCases 10/10; independent default reviewer
`/root/task12_review_retry` APPROVE after two finding batches. All protected-marker
presentations, supported record classes, normalized duplicate keys, quoted scalars,
UTF-8 surrogate input, live ancestor/leaf identities and separate integration
schema were swept. Enumeration: `rg -n 'UNSAFE|scalar\(|replace.*_|walked|PUBLISHED_' plugins/obsidian-wiki/scripts/wiki_access/policy.py`.
Registered reviewer failed unsupported inherit model and earns no review credit.
No private source payloads or historical research fixtures were used. Stage gate
remains pending; workload and store/client evidence remain unproved.

Task 1.3: fresh synthetic development (4 questions) and separately frozen acceptance
(20 questions, five each exact/conceptual/rationale/historical), each with six separate
absent/protected/ambiguous/contradictory/date/partial controls. Both include explicit
claim labels over exact projected source byte spans, modality and event-date limits;
contradiction/date/partial controls have separate labeled notes. No historical research
holdout was copied or reopened. Development and acceptance topic/hash/ID overlap,
empty class denominators, missing labels, changed freezes and implementation-lock drift
refuse. Technical fake-only evidence does not establish real owner query usefulness.

Metrics for later execution: Recall@5 counts the labeled distinct source page among
five distinct page results, reports numerator/denominator by the four classes, and
requires at least 17/20 overall. Exact resolution is scored separately with 100% unique
selection and explicit ambiguity. Controls have separate denominators. Every emitted
citation occurrence must bind to actual read spans; structural validity is separate
from required/unsupported claim labels. CLI timing includes startup, scans and JSON;
warm p95 <=0.5 s, actual RSS <=256 MiB, total pilot state <=128 MiB and every serialized
read <=24,000 bytes. None of these performance/client criteria has run yet. Acceptance
execution paths currently refuse until implemented, preventing invented proof.

Stage 1 gate PASS at 703748b; 18 cases and both pilot wrappers pass after the documented two-round fix-scope repairs. Stage 2 has not started.

context-usage: verdict=handoff now=143928 window=258400 pct=55.7 projected_pct=100.8 disjoint=False reason: rule context: now=143928 of window=258400 (rollout model_context_window) is 55.7% > 50%

Resume Task 2.1 from the canonical plan in a fresh session; branch feat/local-sqlite-wiki-pilot. All child agents and tool sessions completed; dispatch ledger NOT RUN (no log). Private path/frozen manifests in ignored plan-progress state. No active pilot/client route or model/source write was introduced.

Task 2.1 PASS: immutable section-row SQLite schema, exact UTF-8 maps, weighted quoted-OR BM25 5/3/2/1/1, distinct-page ranking and bound SQL. StoreCases 5/5 pass. Independent default Tier-1 store_review: 0 Critical/3 Important; schema/FTS validation, strict malformed-record refusal and direct ranking/map/injection/runtime tests repaired with fix-scope PASS. Frozen research stopwords retained; v1 tokenizer preserves command switches and slash/colon tokens, and ATX splitting ignores fences. No historical recall claim or acceptance opening. Resumption baseline 40/40 wrappers passed.

Task 2.2 PASS: private local generations, complete current-source/policy checks, reader pins, local writer locking, durable immutable publication, revocation and validated reclamation. GenerationCases 9/9 and StoreCases 5/5 PASS. Independent default Tier-1 generation_review diagnosed pathname source-write race, midscan additions, oversized manifests, hardlinked/replaced locks, nested mounts/FIFOs and total-budget retention. Source-write class independently confirmed corrected; every class repaired and directly tested at fix scope. All local mutations bind held directory descriptors; SQLite build now caps pages to remaining aggregate storage after manifest/pointer reservation and removes owned failed staging. Initial new-store pointer absence corrected from actual failure. Enumeration: rg -n "os\.(open|mkdir|replace|unlink|rmdir)|write_private|snapshot" plugins/obsidian-wiki/scripts/wiki_access/generation.py. No source write or real corpus/client query; NFS observations remain host-local.

Task 2.3 PASS: explicit unique/ambiguous/not-found resolution, bounded guarded distinct-page literal search, typed metadata/date filters and aggregate status. LookupCases 3/3 and Stage2IntegrationCases 3/3 PASS on development-only fixtures. Read receipts are absent from discovery; unavailable fields refuse, oversized responses refuse, source/refresh drift discards every buffered disclosure. Missing-guard negative control is detected. Real lookup/performance and Stage 3 evidence/CLI remain unproved.

Stage 2 gate PASS: final regressions 40/40 wrappers (16.020 s), pilot unit 40 cases, integrated four cases; final fix-scope 22 cases. Independent Tier-2 found one Critical SQLite leaf reopen and no Important; round 1/2 fixes construction in memory with held-FD serialization. Independent Critical re-review PASS, hardlink/symlink replacements refuse without source changes. Full sanitized gate report: stage-2-gate.md. No client, acceptance or real-vault query executed. Next Task 3.1.

Stage 2 gate commit 7e85f62. context-usage: verdict=handoff now=157813 window=258400 pct=61.1 projected_pct=111.6 disjoint=False reason: rule context: now=157813 of window=258400 (rollout model_context_window) is 61.1% > 50%

Resume Task 3.1 in a fresh session from the canonical plan, branch feat/local-sqlite-wiki-pilot. All agents/tool sessions completed; ledger NOT RUN (no log). No Stage 3 task started.

Task 3.1 PASS (2026-10-11): ReadCases 4/4; complete one-to-five-note authoritative projections, exact UTF-8 response cap, CRLF/multibyte maps, explicit full-note omissions and whole-bundle stale/unknown-ID refusal. Host mutation proof recorded for the first claim. Resumption baseline 40/40 wrappers PASS. Legacy handoff migrated through the owned v2 writer with original Stage 2 completed-round evidence retained; private context backup remains in the original ignored pack. No acceptance/client/source activation.

Task 3.2 PASS: ReceiptCases 5/5, first-claim signing mutation proof. Stateless versioned domain-separated HMAC binds exact returned evidence/hash/maps/spans/body and full-response bytes, 900-second expiry; admin-only 0600 key creation and explicit rotation. Independent default receipt_review over d54f2f6..working tree: 0 Critical/1 Important rotation-during-final-check race, repaired with deterministic verification and post-seal races plus final signing-state validation. Reviewer 27 additional adversarial checks PASS; no key/body disclosure or private acceptance use.

Task 3.3 PASS: CitationCases 4/4 and first-claim mutation proof. Every requested occurrence verifies exact read-bound UTF-8 quote/source maps; relative full locators disambiguate basenames. Fenced/invented/unknown/unread/raw/escaped targets refuse; supported unique ATX headings and existing alphanumeric/hyphen blocks bind to spans. Duplicate headings counted in authoritative source, including removed provenance, downgrade to page citations. Structural-only verdict never certifies semantic facts or interval continuity. Obsidian internal-link syntax checked against official https://obsidian.md/help/links.

Task 3.4 PASS: CliCases 5/5; real subprocess stdin/stdout, strict size/exit/request separation, resolver precedence, disabled/corrupt stores, source-state containment and private canary sanitation. Independent default cli_review over 3aa3f5b..working tree APPROVE, 0 Critical/0 Important/1 Suggestion; 17 additional request/config checks and synthetic resolver controls PASS. Config mount-locality suggestion remains optional; derived-state locality is mandatory, config ownership/link/private-mode checks explicit in docs. Final config/root selection is rechecked before disclosure. Admin-only refresh/check/key-rotation and exact executable operations documented. First-claim CLI mutation proof PASS. Stage 3 integration/full gate pending.

Stage 3 gate PASS (2026-10-11): remediation 2/2; full entry 39/40 wrappers (21.431 s), failed unit wrapper repaired and 60/60 PASS (4.484 s), affected integration 5/5 PASS (1.955 s). Independent stage3_review Critical re-review APPROVE at ca3cf51; prior two Important findings addressed. Detailed report stage-3-gate.md. Core technically complete on synthetic fixtures; Stage 4 Task 4.1 next. No client, acceptance, real-vault or adoption proof. Legacy ledger advisory for native agent syntax; actual native review receipts retained.

Task 4.1 PASS: AdapterCases 2/2 and scoped grants PASS; command-only exact read executable, single get/24000 cumulative cap and explicit opt-in routing. Required cli_review 0 Critical/1 Important file-back bypass repaired: draft hands off to guarded publication, maintenance/base hashes checked before every mutation; lookup never directly mutates page/log. First-claim mutation proof. Actual client still pending Task 4.3.

Task 4.2 PASS: Packaging 3/3 + Stage4Integration 1/1 copied installed layout; stdlib and executable modes, recursive syntax 51 sources, installed rotation/revocation and no retrieval source writes. Operator refresh/recovery/local-state/errors documented; Cursor remains original manual path. First-claim installed-entry mutation proof. Task 4.3 next.

Task 4.3 partial at21ba7d4: locked independent synthetic20/20 recall,60/60 exact,50/50 citation occurrences; class5/5 each, six structural controls1/1. CLI p950.067058s, peak childRSS21,520KiB, state199,006bytes,maxread4,349bytes; installed live tracePASS. Full regressions41/41 (31.370s),71 pilot cases,six integrated cases. Code lock still validates; original independent set consumed once, private artifacts retained. Client preflight exits4 BLOCKED, zero calls: hard$1 limit not enforceable by documented estimated cap. Task4.3/Task4.4/final gate remain incomplete, private-source path unqualified, pilot inactive. Resume dependency: verified hard cap or explicit owner amendment, then actual client execution/validation. Detailed sanitized results stage-4-status.md. All owned sessions/reviewers complete; unstopped0.
