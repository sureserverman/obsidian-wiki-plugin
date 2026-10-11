# Local SQLite wiki pilot results — 2026-10-11

Core technically complete; opt-in command adapter and copied-package operation
implemented. Full Stage 4 and the whole plan remain incomplete at Task 4.3.
Pilot inactive. No real-wiki model call, configured-client trace or adoption.

Implementation: branch `feat/local-sqlite-wiki-pilot`, core gate `b20cfaa`,
adapter `37e9929`, packaging `78bb7b1`, locked model-free runner `21ba7d4`.
Canonical plan/architecture: `2026-10-09-local-sqlite-wiki-pilot-plan.md` and
`2026-10-09-local-sqlite-wiki-pilot-architecture.md`.

| Evidence | Actual result | Scope |
| --- | --- | --- |
| Frozen independent Recall@5 | 20/20 (100%); 5/5 each exact/conceptual/rationale/historical | Fresh synthetic questions; separate from development |
| Exact path/title/alias resolution | 60/60 | Actual copied installed CLI |
| Read-bound citation occurrences | 50/50, including duplicates | Structural provenance; no semantic answer verdict |
| Absent/protected/ambiguous/contradictory/date/partial controls | 1/1 each | Model-free lookup/evidence only; client answer judgment pending |
| Warm end-to-end search p95 | 0.067058 s, 20 queries | Includes startup, scans and JSON; host/fake corpus |
| Cold unavailable status / refresh | 0.042748 / 0.066234 s | Host/fake corpus; no NFS timing promise |
| Observed peak child RSS | 21,520 KiB | Linux RUSAGE_CHILDREN peak for actual CLI subprocesses |
| Total pilot state / maximum read response | 199,006 / 4,349 bytes | Below 128 MiB / 24,000-byte limits |
| Installed live CLI trace | PASS, 0.707 s | Fresh fake build/lookup/get/verify, then revoke and refuse old/buffered evidence |
| Stage4IntegrationCases | 1/1 PASS, 0.567 s | Installed rotation, revocation, source preservation, disabled/admin separation |
| Full plugin regression | 41/41 wrappers PASS, 31.370 s | 71 pilot cases, six integrated cases, recursive syntax 51 Python sources |
| Configured-Claude permission matching and claim support | BLOCKED, zero calls/traces | Hard spend bound not established; no fabricated answers credited |
| Real-vault lookup / owner usefulness | Pending / pending | No current private question set or source qualification receipt |

The implementation lock was created before opening the original independent set.
Lock-file SHA256: `d541737aa9cb21be5401b1fcde7a392ff23cb1a3dd5b028432d2542aa967188c`. Opened manifest canonical hash:
`4fe63607081f75fdd20fb097982f5caae1c3d0894603de61403dec9d6b9e2062`. The exclusive private consumption marker remains;
this set will not be rerun for an independent claim. Any locked code change retires
this receipt for the changed implementation and requires a new independent set.
The same lock still validates after acceptance and regressions.

Actual payload-bearing CLI events, source before/after inventories, manifests,
timed receipts and implementation lock remain 0600 in the original local 0700
execution pack outside Git/vault. No source payload or private security report
is copied here. Retrieval left fixture source inventories unchanged; revocation
was an explicit fixture mutation. Historical research holdouts were not reopened.
The independent run succeeded once in 10.013 seconds.

review: Tier-1 Task 4.1 default agent /root/cli_review over b20cfaa..Task-4.1 working tree — 0 Critical/1 Important file-back bypass; fixed guarded-writer handoff and maintenance/base-hash obligations, AdapterCases2/2 and scoped-grant regression PASS.
review: Tier-2 default agent /root/stage4_review over b20cfaa..Task-4.3 working tree, plus narrow lock-flow follow-up — 0 Critical; duplicate same-note get, trace creation permissions, optional aliases and FIFO input refusal fixed. Alias/dedup/0600 fixes independently confirmed; final FIFO fix closes on direct nonblocking refusal test and full 71-case regression. One optional Write-grant Suggestion remains.

dispatch: 0 of 0 rostered worker tasks dispatched; 3 started Stage 4 tasks inline;
0 table-routed inline. Task 4.3 assessment incomplete; Task 4.4 not started.
ledger: actual native reviews and start/stop receipts; legacy parser advisory for
native naming/dispatch-description rows; unstopped zero. No client-proof substitute.
evaluator: final Stage 4 judgment NOT RUN — actual configured-client evidence missing;
no whole-plan/final-gate PASS asserted. Stage 3 spent two of two remediation rounds;
Stage 4's remediation account remains zero, with no fabricated gate pass.

## Resume at Task 4.3

Claude Code 2.1.296 is installed. The actual local client preflight exited 4 with
BLOCKED, zero model calls and zero traces. The approved Task 4.3 requires total
maximum $1.00, six fixed fake-only traces, 150 seconds each, no retry/model override
or global configuration edit. It explicitly says: “If the client cannot enforce/record
the budget or is unavailable, keep its support status BLOCKED and the default route
unchanged.” Official CLI documentation describes `--max-budget-usd` as an estimated
cap that can be exceeded: https://code.claude.com/docs/en/cli-reference#flags.
No verified provider-side hard total bound exists in this execution evidence.

Required dependency: establish a verified hard spend bound on the existing route,
or obtain explicit owner amendment accepting estimated cap enforcement for the six
fake-only traces. Then finish actual client execution/trace validation and claim-level
judgment; current client mode only performs fail-closed preflight. Do not mark
permission matching or semantic support passed from unit fixtures. The private-source
mode also reports pending qualification explicitly; it is not a completed live-source
runner. Representative private questions/source qualification and owner usefulness
remain separate pending follow-ups, never inferred from synthetic results.

Task 4.4's project-local DEC, architecture/results close-out and final Stage 4
judgment remain due after required Task 4.3 evidence. Keep DEC-001/002/003 and
GDEC-SEC-001 in force. Optional config-file locality and unused Write-grant
Suggestions remain recorded; neither is a claim of normal adoption.
