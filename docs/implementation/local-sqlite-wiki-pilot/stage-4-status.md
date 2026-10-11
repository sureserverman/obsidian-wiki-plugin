# Local SQLite wiki pilot status — 2026-10-11

The model-free core and bounded configured-Claude fake-client flow are technically
qualified on synthetic evidence. All fourteen implementation tasks and the four
declared Stage 4 gate checks are complete. [Final gate](stage-4-gate.md) records
the actual evidence and audit limitations. Real-vault lookup and owner usefulness are pending.
The pilot remains opt-in with owner-local configuration disabled by default;
normal adoption, other hosts and broader content egress were not selected.

Branch: `feat/local-sqlite-wiki-pilot`; core gate `b20cfaa`. The six latest actual
client traces ran product commit `5151290`. Their original results are preserved.
The later scorer correction and read-cap recovery guidance have separate,
model-free evidence; they are not a new provider execution of the revised command.

## Current receipts and qualification scopes

Private execution packs are local 0700 directories with 0600 files, outside Git
and the vault. Linked results contain the checkable receipts; this document records
sanitized aggregates. Research holdouts were not reopened.

| Check | Actual result | Receipt / scope |
| --- | --- | --- |
| Fresh independent v7 Recall@5 | 20/20; 5/5 each exact/conceptual/rationale/historical | [v7 result](/tmp/wiki-pilot-label-coverage-20261011-b1ya4qqc/independent-v7-result.json), synthetic installed CLI |
| Exact path/title/alias resolution | 60/60 | Same v7 receipt, complete eligible-source candidate oracle |
| Read-bound citation occurrences | 50/50 | Same v7 receipt, structural provenance |
| Absent/protected/ambiguous/contradictory/date/partial controls | 1/1 each | Same v7 receipt, model-free evidence behavior |
| Warm search p95 | 0.064007 s | Same v7 receipt; startup/scans/JSON included |
| Cold unavailable status / refresh | 0.046675 / 0.067497 s | Same v7 receipt, host |
| Peak child RSS | 22,124 KiB | Same v7 receipt, Linux RUSAGE_CHILDREN |
| State / maximum serialized read | 194,886 / 4,389 bytes | Same v7 receipt, below 128 MiB / 24,000 bytes |
| Latest configured client flow | 6/6 frozen facts and abstention; 8/8 citations; max read 4,377 bytes | [offline revalidation](/tmp/wiki-client-inline-schema-20261011-3hi_4gnb/offline-rescored-result.json), original `5151290` actual outputs |
| Actual-answer independent judgment | 0 Blocking; all six factual cases and eight citations pass; one Material recovery-advice defect | [original judgment](/tmp/wiki-client-inline-schema-20261011-3hi_4gnb/independent-answer-judgment.json), unchanged historical FAIL |
| Material recovery-advice repair | Fixed at command-source scope, boundary review approved | [closure](/tmp/wiki-client-inline-schema-20261011-3hi_4gnb/material-closure.json); no later provider call |
| Regression after scoring/advice repair | 41/41 wrappers; 79 pilot tests; six integration cases; 53 Python sources syntax checked | [regression log](/tmp/wiki-client-inline-schema-20261011-3hi_4gnb/coverage-repair-regression.log), host |
| Current command status text / workload checks | AdapterCases and WorkloadCases pass | [scoped log](/tmp/wiki-pilot-label-coverage-20261011-b1ya4qqc/current-adapter-workload.log), host |
| Real-vault lookup / owner usefulness | Pending / pending | Representative current private workload and owner grading not run |

V7 implementation-lock canonical SHA256:
`f25756ef7f89d6599fbe79bf79c4a23b5594d9879403d8b5299b0138de792190`.
[V7 lock](/tmp/wiki-pilot-label-coverage-20261011-b1ya4qqc/implementation-lock-v7.json)
contains all 36 required files and is validated before and after execution.
Manifest canonical SHA256:
`5d9b4be667feb2be836bd8950bb63a86c39b5b2bcd0d1f8a09057e1939b29de0`.
Original and v2–v6 sets were opened once and retired after implementation changes.
V7 uses newly frozen topics distinct from development and prior acceptance topics.
No retired set was rerun for an independent quality claim.

## Six actual client traces at 5151290

The owner's carry-on authorization permitted six fresh fake-only launches under
an estimated $1 total with accepted possible overshoot, 150 seconds each, no
automatic retries, model override or global settings edits. All six are consumed;
actual cost $0.7172794, overshoot $0. Configured Claude 2.1.296 was used. Immutable
launch/stdout/receipt files are in the local
[client run](/tmp/wiki-client-inline-schema-20261011-3hi_4gnb/client-799dbe1fa98bb8ff0b24d2c8948ef5a392dd1200bd39a34a480a9ef146ad843f).

| Case | Cost USD | Actual fact / abstention result |
| --- | ---: | --- |
| exact | 0.1378196 | Required checkpoint instruction, one verified citation |
| alias | 0.1171650 | Alias resolves; required checkpoint instruction, one verified citation |
| missing/protected | 0.0600890 | Both unavailable; abstains, no access code/canary/citation |
| date | 0.1664768 | March 1 offline and March 7 online; interval unknown, three verified citations |
| contradiction | 0.1689618 | Both dated observations; current state unknown, three verified citations |
| oversized | 0.0667672 | Complete page omitted, no read receipt; correct abstention, faulty cap advice repaired separately |

Source inventories were unchanged; observed durations 10.237–32.138 seconds.
No raw fallback, second get, refresh, broad shell, automatic retry or unsupported
source claim occurred. Every displayed citation was independently checked against
its authenticated read receipt, generation, page ID, exact UTF-8 quote/offsets
and native valid/verified fields. Temporary owner-only configured auth/routing
was removed after execution. The deny-only hook rejects unrelated commands and
never approves permissions. Plugin lifecycle hooks are disabled in the transient
harness; complete plugin lifecycle behavior is outside this qualification scope.
No real-wiki content was sent to the model.

The original automated result failed the date/contradiction coverage predicate:
a frozen label contains two sentences while the model verified each separately.
The repaired scorer covers the exact frozen passage using intervals from the
same authenticated page and allows only whitespace gaps. Missing sentences,
missing words, altered frozen text or another page still refuse. A genuine RED
regression preceded the repair; independent review revalidated all six immutable
outputs. Original result, lock, launch identities, labels and stdout are retained;
the separate correction records every input stdout hash and scorer hash.

The independent actual-answer evaluator returned FAIL only for advice to raise
the fixed read cap. The command now explicitly preserves 24,000 bytes, distinguishes
admin refresh from source editing, and requires separate owner-selected guarded
maintenance before any later refreshed answer. The original faulty answer and
judgment remain unchanged. This source repair does not prove future model advice.

## Reviews, decisions and remaining gate

review: required Task 4.3 boundary default agent `/root/cli_review` over the scorer
and recovery-guidance fix — APPROVE, 0 Critical/Important/Suggestion. Fifteen
focused checks and eight independent coverage controls passed; all six original
traces revalidated. Prior containment, native here-string, installed-schema and
exact-resolution review findings are fixed; historical receipts remain private.

evaluator: fresh default `/root/client_answer_judgment_v3`, briefed only on goals,
criteria and artifact locations — 0 Blocking / 1 Material / 0 Minor at `5151290`;
factual support 6/6, citations 8/8. Material repaired at source/fix scope above.
Final Stage 4 Tier-2 `/root/stage4_review` over `b20cfaa..faceb85` and Task4.4
document fix scope: APPROVE, 0 Critical/Important. Fresh default evaluator
`/root/final_pilot_judgment`: PASS, 0 Blocking/Material/Minor remaining.
[Final judgment](/tmp/wiki-pilot-label-coverage-20261011-b1ya4qqc/final-judgment.json).

DEC-001: existing project eligibility/containment consumers unchanged.
DEC-002: strict unknown request/source shapes refuse; scoring rejects unsupported
labels and gaps. DEC-003: file-back uses the existing owner-confirmed maintenance
and base-hash guarded writer; lookup has no source-writing authority.
GDEC-SEC-001: no private payload or security-report body copied into canonical docs.
Project-local selected architecture is recorded in [DEC-004](/mnt/vault/Portfolio/ai-tools/obsidian-wiki-plugin/decisions.md).

dispatch: 0 of 0 rostered worker tasks; all fourteen declared tasks inline.
Required review/evaluator agents performed review roles. Stage 4 final verification
passed in its first recorded round; no final-gate remediation was needed.
Stage 3's saved 2/2 account is preserved. Plugin version is0.11.0; no merge/publish.
Final installed integration1/1, live CLI build/lookup/get/verify/revoke and full
regression41/41 pass; [final gate](stage-4-gate.md) links every actual receipt.

## Historical spend and proof limitations

| Consumed allowance | Launches | Cost USD | Result at that time |
| --- | ---: | ---: | --- |
| Initial qualification | 6 | 0.2832846 | Native heredoc permission denials |
| Permission diagnostics | 2 | 0.0634152 | Both native denials; offline parser isolated heredoc rejection |
| Here-string qualification at 6c12c66 | 6 | 0.4116868 | Status succeeds; incomplete request schemas |
| Inline-schema qualification at 5151290 | 6 | 0.7172794 | Complete frozen factual and abstention flow; recovery advice repaired separately |
| Total | 20 | 1.4756660 | No automatic retries or additional paid launches |

The canonical vault plan has no pre-execution audit baseline or Git history;
full historical plan-flip audit is NOT RUN. Earlier available checks found
missing Stage 1 records, prior-tree Stage 3 fingerprints and Stage 2 commit-title
advisories. Current proof records are reconciled to their actual commit trees: contract,
policy, reads, receipts, citations, CLI, adapter, packaging and acceptance sensitivity
are proven today. Workload test-harness and external canonical-document mutation
limitations are recorded as deviations; later proofs cannot certify historical
test-first ordering. The [final audit](/tmp/wiki-pilot-label-coverage-20261011-b1ya4qqc/final-plan-audit.json)
has zero Blocking findings, five named advisories and historical1/3/5 NOT RUN. Do not create a retrospective baseline or describe
this historical audit as passing. See [progress](progress.md) for retained stage
history and [original audit](/tmp/wiki-pilot-amended-20261011-ladm22rq/final-plan-audit.json).
