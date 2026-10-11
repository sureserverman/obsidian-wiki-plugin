# Stage 4 final gate — 2026-10-11

PASS for the four declared technical checks and bounded synthetic implementation.
All 14 tasks are implemented. The original provider execution, later model-free
repairs and unavailable historical audit checks have distinct statuses below.
Real-vault lookup and owner usefulness remain pending; normal adoption is inactive.

The tested artifact is `faceb85`, obsidian-wiki 0.11.0. This close-out adds reports;
product source and the 36-file v7 lock remain unchanged after the final checks.
[Artifact receipt](/tmp/wiki-pilot-label-coverage-20261011-b1ya4qqc/final-artifact-receipt.json)
binds every final receipt by SHA256 and records zero new provider launches.

| Declared check | Actual result | Host evidence |
| --- | --- | --- |
| `python3 tests/wiki_access_cases.py Stage4IntegrationCases` | 1/1 PASS | [integration log](/tmp/wiki-pilot-label-coverage-20261011-b1ya4qqc/final-integration.log), copied installed package |
| `python3 tests/wiki_access_acceptance.py --suite live-cli --source fixture` | PASS | [result](/tmp/wiki-pilot-label-coverage-20261011-b1ya4qqc/live-cli-result.json), [12 actual subprocess events](/tmp/wiki-pilot-label-coverage-20261011-b1ya4qqc/live-cli-trace.json); build/lookup/get/verify then old verify/get/search refuse generation_stale with no value |
| `bash tests/run.sh` | 41/41 wrappers PASS; 79 pilot cases; six integration cases; 53-source syntax coverage | [final regression](/tmp/wiki-pilot-label-coverage-20261011-b1ya4qqc/final-regression.log), host; buffered-output source/config drift controls included |
| Independent architecture/disclosure and actual-answer judgment | PASS; 0 Blocking / 0 Material / 0 Minor remaining | [judgment](/tmp/wiki-pilot-label-coverage-20261011-b1ya4qqc/final-judgment.json), fresh default evaluator `/root/final_pilot_judgment` |

Independent v7 installed acceptance: 20/20 Recall@5 (5/5 per class), 60/60 exact
resolutions, 50/50 read-bound citation occurrences, six structural controls 1/1.
Warm end-to-end search p95 0.064007 s, peak child RSS 22,124 KiB, state 194,886 bytes,
max serialized read 4,389 bytes. [Receipt](/tmp/wiki-pilot-label-coverage-20261011-b1ya4qqc/independent-v7-result.json).
The full 36-file lock validates after all mutations and final checks. V7 was opened
once; original/v2–v6 opened sets were retired after implementation changes.
Historical research holdouts remain untouched.

Actual configured-Claude evidence covers six fake-only launches at 5151290,
cost $0.7172794, no overshoot/retry, unchanged source inventory, maximum read 4,377 bytes.
All 6 frozen facts/abstentions and 8 displayed citations independently checked:
exact UTF-8 quoted bytes/offsets, page IDs, authentic reused receipts, generations
and native valid/verified flags. Date/contradiction answers retain March 1 offline
and March 7 online observations, with continuity/current state explicitly unknown.
[Original-trace revalidation](/tmp/wiki-client-inline-schema-20261011-3hi_4gnb/offline-rescored-result.json).
This is semantic support beyond link resolution.

Original automated date/contradiction failures were a scorer false negative:
one frozen label contains two separately verified sentences. Exact-page interval
coverage now permits only whitespace gaps; missing facts/text/labels refuse.
Original traces/results and labels were preserved, with a separate input-hashed
rescoring receipt and genuine RED/green regression. The original oversized answer
also offered an invalid raise-cap remedy; its original FAIL judgment remains.
Current command source fixes the fixed cap/admin/guarded-maintenance guidance,
with [separate closure](/tmp/wiki-client-inline-schema-20261011-3hi_4gnb/material-closure.json)
and independent review. No provider execution of revised advice is claimed.
Twenty cumulative authorized launches consumed $1.475666; no further call authorized.

## Review and protocol accounting

review: Tier-2 required native default `/root/stage4_review` over `b20cfaa..faceb85`
and final Task 4.4 document fix scope — APPROVE; 0 Critical / 0 Important. Prior complete
source exact-resolution scoring Important is fixed. Sixteen scoped tests and
three independent UTF-8 controls pass; all6 original traces independently rescored.
The historical ask-skill link Suggestion was repaired with d263330 context.

review: required Task4.3 boundary native default `/root/cli_review` over scorer
and cap-guidance repair — APPROVE; 0 Critical / 0 Important / 0 Suggestion; 15 focused tests,
eight independent coverage controls, six immutable traces and eight citations checked.

evaluator: fresh native default `/root/final_pilot_judgment`, briefed only on plan
goal, Stage 4 goal, criteria and artifact locations — PASS; 0 Blocking / 0 Material / 0 Minor
remaining. It read actual client stdout, 158 independent installed events, 12 live
subprocess events, source and final runtime logs. Historical Material is retained
and closed at fix scope, without invented later provider execution.

dispatch: 0 of 0 rostered worker tasks dispatched; 14 declared-inline tasks, 0 table-routed
inline. Plan-wide dispatch checker exits 0. Required reviewer/evaluator roles are
separate. Stage 4 first recorded verification round passes; no final-gate repair
needed. Saved Stage 3 account 2/2 remains. No applicable platform verifier exists
for this stdlib CLI; actual installed host checks above are the runtime evidence.

## Current records and historical audit limits

[Final record audit](/tmp/wiki-pilot-label-coverage-20261011-b1ya4qqc/final-plan-audit.json)
exits 4 with 0 Blocking and five advisory findings:

- Task 1.3 test-harness validator mutation is prohibited by prove-claim; executed
  corruption/lock/denominator controls pass, formal mutation-proof limitation
  disclosed as a tool-written deviation.
- Task 4.4 criterion concerns canonical documents outside Git; actual link/status/
  privacy/conformance checks and independent review pass, repository mutation
  cannot certify external canonical history. Tool-written deviation retained.
- Task 2.1/2.2/2.3 title matcher sees no task IDs in commit subjects. Actual per-task
  commits are ac421b0/65781ec/ab31956 and their bodies name the respective tasks,
  test results and executor; no history rewrite or retroactive title change.

Historical findings 1/3/5 are NOT RUN: canonical vault plan has no Git history or
original pre-execution baseline. No retrospective snapshot was created. This is
not a clean full-history audit. Missing current contract/policy proofs and prior-tree
Stage 3 fingerprints were reconciled with today's reversible sensitivity proofs,
bound to the commit each record accompanies. Exact product bytes were restored
and v7 lock rechecked; current proofs do not certify historical test-first order.

## Decisions, workflows and handoff

ARCH-01–ARCH-09 conform; [DEC-004](/mnt/vault/Portfolio/ai-tools/obsidian-wiki-plugin/decisions.md)
records selected ARCH-01–ARCH-10, stdlib JSON CLI, explicit ask route, MCP-now rejection
and accepted startup/source-scan/manual-refresh/cap costs. DEC-001 project eligibility
helper and consumers unchanged; DEC-002 unsupported source/request/receipt shapes
refuse; DEC-003 lookup does not write sources and file-back uses existing confirmed
maintenance/base-hash writer; GDEC-SEC-001 canonical documents contain aggregates
and reasons, no private payload/security-report bodies.

Workflow audit over d263330..faceb85: WF-WIKI-LOOKUP extended, contract preserved;
WF-CHAT-IMPORT, WF-CHAT-PUBLISH, WF-VAULT-WRITE-MAINTENANCE untouched. No behavior
removed. [Document check](/tmp/wiki-pilot-label-coverage-20261011-b1ya4qqc/task44-document-check.json).
No backlog entry closes; existing BL-022 session-storage documentation is outside
this pilot. Optional config-file mount-locality and inherited Write-grant
suggestions remain disclosed; derived-state locality/read Bash grant are enforced.

[Operator handoff](operator-handoff.md) and [status/results](stage-4-status.md)
separate core, adapter, current-source retrieval and owner usefulness. Private
source questions/real-vault performance and owner usefulness are pending, restricted
plugin lifecycle remains unqualified, normal adoption / other hosts / broader egress
remain unselected. No merge, push, publish or activation performed. Plugin 0.10.0 → 0.11.0;
marketplace entry has no mirrored version field and membership is unchanged.
