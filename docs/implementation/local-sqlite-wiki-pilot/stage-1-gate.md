# Stage 1 gate

PASS on 2026-10-09: source policy, strict contracts and separately frozen fresh
synthetic workload are complete. No store, read receipt, CLI, client support,
real-vault quality or owner usefulness is claimed.

Stage-scope regression at `a79bf80`: 40 wrappers, 39 PASS, one pilot-integration
import-path failure; 15.03 seconds. Remediation round 1 at `b7e0ffe`: root cause
was runpy not setting the test-directory import path. The pilot integration
wrapper and all new cases then passed. The unchanged 39-wrapper result stands.

Independent Tier-2 reviewer `/root/stage1_review` (default agent, code-review role)
read `d263330..a79bf80` plus `b7e0ffe`; REQUEST_CHANGES, zero Critical, four Important.
Round 2 at `033a3af` repaired strict nested control shapes, class-specific
required/date/support constraints, normalized question duplicate/development overlap
checks and closed response/error envelopes. Fix-scope verification on that committed
revision: both pilot wrappers PASS, 18 unit/integration cases PASS; frozen private
manifests still pass with unchanged fingerprints. The reviewer found no Critical
class, so the gate closes on fix-scope evidence without a repeated review dispatch.
No redesign replaced reviewed functions. No acceptance execution or tuning occurred.

Enumeration commands: `rg -n 'runpy.run_path|wiki_access_acceptance' tests/` and
`rg -n 'for .* in|event_date|required|support|query|def (response|error)' tests/wiki_access_acceptance.py plugins/obsidian-wiki/scripts/wiki_access/contracts.py`.
The defect set includes every nested note/question/control/support field and both
public envelope constructors. New controls reproduce malformed/erased label, date,
endpoint, duplicate-query, bad scalar and private error-code cases.

review: Tier-2 independent default agent over `d263330..a79bf80` + `b7e0ffe` —
0 Critical, 4 Important repaired at `033a3af`; no inline substitution.
review: Task 1.2 independent `/root/task12_review_retry` — APPROVE, 0 residual
Critical/Important; initial registered reviewer failed and earns no credit.
evaluator: not run — no judgment check at this gate.
dispatch: 0 of 0 rostered tasks dispatched; 3 declared-inline tasks.
ledger: not run (Codex logs no dispatch lines; DEC-039).
platform/fidelity hooks: not applicable to this Python CLI/plugin stage.
Decisions checked: DEC-001 distinct project policy untouched; DEC-002 strict
unsupported inputs; DEC-003 no source writes; GDEC-SEC-001 no private content in Git.
Existing three publication/import contracts are preserved.

Development has 4 questions; acceptance has 20 balanced questions plus 6 separate
controls. Main recall queries/topics/IDs/source hashes have no development overlap.
Generic negative-control question wording is intentionally shared between sets;
controls have separate notes, IDs, labels and denominators, and never enter the
single-note Recall@5 numerator. Corpus is synthetic technical evidence. Fresh
private owner questions, actual runtime/client proof and product acceptance remain
pending. Remediation: 2 of 2 rounds, all Important fixed; no Critical remains.
