# Local SQLite wiki pilot status — 2026-10-11

Stage 3's model-free core is technically complete on synthetic evidence. Tasks
4.1–4.2 are implemented. Task 4.3, Task 4.4 and the final Stage 4 gate remain
incomplete. The configured Claude adapter failed qualification; the pilot remains
inactive. No real-wiki answer-model run or normal adoption was selected.

Branch: `feat/local-sqlite-wiki-pilot`; core gate `b20cfaa`, adapter `37e9929`,
packaging `78bb7b1`, initial acceptance runner `21ba7d4`. This progress change
adds actual client traces and current-source qualification tooling, repairs
qualification containment and exact-resolution scoring, and records the blocker.
It is a partial Task 4.3 commit, not a green task or gate.

## Current local evidence

| Check | Actual result | Qualification scope |
| --- | --- | --- |
| Fresh independent v4 Recall@5 | 20/20; 5/5 each exact/conceptual/rationale/historical | Synthetic installed CLI; separate development topics |
| Exact path/title/alias resolution | 60/60 | Synthetic installed CLI |
| Read-bound citation occurrences | 50/50, including repeated citations | Structural provenance only |
| Absent/protected/ambiguous/contradictory/date/partial controls | 1/1 each | Model-free evidence behavior; actual answer handling unqualified |
| Warm search p95 | 0.061530 s | Host end-to-end CLI, including startup/scans/JSON |
| Cold unavailable status / refresh | 0.047730 / 0.064539 s | Synthetic host measurements |
| Peak child RSS | 21,832 KiB | Observed Linux RUSAGE_CHILDREN peak |
| Total state / maximum read response | 194,886 / 4,389 bytes | Below 128 MiB / 24,000-byte limits |
| Installed live CLI | PASS | Fresh fake lookup/get/verify, then revocation and old/buffered evidence refusal |
| Stage4IntegrationCases | 1/1 PASS, 0.523 s | Installed key rotation/revocation, source preservation, disabled/admin separation |
| Full regression | 41/41 wrappers PASS; 76 pilot tests | Actual discovery runner; six integration cases; 53 Python sources syntax checked |
| Configured client traces | 0/6 qualified; $0.2832846 total | Actual Claude Code 2.1.296, configured `claude-opus-5-5[1m]` |
| Real-vault lookup / owner usefulness | Pending / pending | Runner implemented; representative current private workload not supplied/run |

Current lock SHA256: `c4cb3660afa94bfefffb946b22a3f0156fdd75aa0534179cdd912b6592c2c2a7`.
Independent v4 manifest canonical hash:
`4f3140e7adc7f51c605ef0ea8c57f6ed6b10a26aad593fab4989d2a7d8772e88`.
The complete 36-file lock was validated before and after acceptance and final
checks. The original acceptance set and v2/v3 sets were each opened once; code
changes retired their implementation-specific receipts. None was rerun as an
independent quality claim. V4 was frozen after the final scoring/command-disclosure
fixes. Historical research holdouts remain untouched.

Private manifests, consumption markers, locks, actual client stdout/stderr,
launch/cost receipts and model-free traces remain in a local 0700 execution pack,
with 0600 files outside Git/vault. Canonical documents contain sanitized aggregates.
A regression started during a deliberate mutation proof was invalid (40/41),
discarded, and replaced by a full passing run after restoration. The committed
first-claim proof detects a deliberately broken search and restores product code.

## Actual client result

The owner's 2026-10-11 amendment accepted an estimated $1 total cap, with possible
overshoot, for the six fixed fake-only traces, 150 seconds each, no automatic
retry, model override or global configuration edit. All six launches are consumed.
Recorded overshoot is $0; no further provider calls were made.

| Case | Recorded cost USD | Actual result / independent semantic judgment |
| --- | --- | --- |
| exact | 0.0856998 | Initial status denied; required checkpoint instruction absent |
| alias | 0.0552720 | Initial status denied; alias and required instruction absent |
| missing/protected | 0.0357778 | Initial status denied; safe refusal, admission behavior unexercised |
| date | 0.0361574 | Initial status denied; both dated observations absent, no continuity asserted |
| contradiction | 0.0358658 | Initial status denied; both observations absent, no present state asserted |
| oversized | 0.0345118 | Initial status denied; no cause invented, omission behavior unexercised |

All actual traces attempted the dedicated read executable once for `status` and
received the client's native `dontAsk` denial. No successful read or emitted
citation occurred. Every trace stayed below 150 seconds (observed range about
6–10 seconds; first recovered duration is client-reported). Zero unsupported
source claims were observed, but all-abstention answers to answerable questions
fail Task 4.3. Client process success is not qualification success.

The first trace's runner stopped on a non-object system notice. Its original
launch remains consumed; cost/model/duration were recovered offline from actual
stdout, without a retry. Only the five unlaunched cases ran after parser and
containment fixes, under a separately recorded implementation lock. Their fake
source inventories were unchanged. The aggregate retains the first trace's
original implementation identity; it is not a single-current-lock passing run.

Qualification sessions copy existing configured auth/model routing into temporary
owner-only configuration, remove it afterwards, disable model tools except Bash,
and use a deny-only hook to reject every command except strict literal-JSON stdin
to the dedicated read executable. Import/hook failures block. The hook does not
approve the packaged grant. Existing plugin lifecycle hooks are disabled in the
transient qualification copy to prevent session enumeration; complete plugin
lifecycle behavior is not qualified by this harness. No CLI allow-list override
was used to mask frontmatter matching. Global settings were not changed.

Model-free diagnosis confirms both `ask` and `legacy-ask` were registered in actual
client initialization. The natural-language skill has a distinct name and no
shell grant; manual `ask` has model invocation disabled and the scoped executable
grant. Claude's local command validator passes. No managed-settings file or
settings.d directory was found; user permissions contain only a default mode.
These checks do not explain or fix the native grant denial. The executable's
stdin interface works in installed subprocess tests. Actual permission matching
remains unresolved; do not promote the trailing-wildcard candidate to qualified.

## Reviews and architecture

review: required Task 4.3 boundary default agent `/root/cli_review` — final APPROVE,
0 Critical/0 Important. Fixed configuration/ambient environment escape, raw-Bash
read bypass, deny-hook import/failure handling, unknown/duplicate expense records,
and uncited negative-case links. Twelve scoped cases and independent adversarial
controls passed; no provider calls were credited as passing.

review: required Stage 4 default agent `/root/stage4_review` over `b20cfaa` through
the working tree — 0 Critical/1 Important. Fixed exact-resolution scoring against
all eligible source projections, including notes outside the question set;
compare the complete ordered locator list and unique/ambiguous state. Class sweep
covers path/title/alias, unrelated extra candidates and actual legitimate
ambiguity. Ten AcceptanceRunnerCases pass; corruption now fails 40/60 selections.

judgment: fresh default agent `/root/stage4_judgment`, briefed only on goal, stage
goal and gate criteria — FAIL, 1 Blocking/1 Material. Blocking: actual client
lookup/read/citation and date/contradiction answer support remain unexercised.
Material: ARCH-02 omitted the implemented generation-to-store dependency. The
architecture amendment explicitly records refresh's pure build/schema/recipe
edge; the full import-edge sweep confirms store depends only on contracts/stdlib,
so admission remains in policy and publication in generation. No cycle, source
writer, provider dependency or alternate admission policy is introduced.

DEC-001: existing project containment and vault-context consumers remain outside
pilot admission. DEC-002: strict source/request/error shapes refuse visibly.
DEC-003: file-back delegates to the existing maintenance/base-hash guarded writer;
lookup adds no source-writing authority. GDEC-SEC-001: payloads and security-report
bodies remain local; canonical results contain aggregates only.

dispatch: 0 of 0 rostered worker tasks; Tasks 4.1–4.3 inline, Task 4.3 incomplete.
Review/evaluator agents performed their required roles, not implementation tasks.
Stage 4 remediation remains 0 completed rounds: these are Task 4.3 repairs and
preliminary gate evidence, not a completed final-gate round. Stage 3's saved 2/2
account is preserved. Required final-gate judgment remains failed; Task 4.4 and
final close-out are not passed.

## Resume dependency

Resume Task 4.3 by diagnosing the native client grant mismatch with a narrowly
controlled fake-only comparison, then fixing and qualifying the packaged route.
The six-case allowance has been consumed. Additional paid diagnostic or acceptance
launches require explicit owner authorization; remaining dollars do not authorize
a seventh trace. No automatic retry or permission bypass is selected.

A proposed diagnostic comparison would retain the current deny-only shell guard,
Bash-only tool surface, fake vault, isolated configured route and 150-second limit.
One control would add a session-only literal grant for the exact fake read
executable; another would isolate the packaged frontmatter grant. Neither control
would establish packaged-client acceptance. Record costs and actual status events,
then freeze fresh acceptance labels after any implementation change. No real-wiki
model data, generic shell/interpreter grant or global configuration write is needed.

Representative private source qualification and owner usefulness stay separately
pending. Task 4.4's selected project-local DEC and final close-out follow Task 4.3.
Keep the existing DEC IDs in force and the pilot inactive.

## Post-commit audit limits

The plan-flip audit was run after the progress commit. Its full verdict is NOT RUN:
the vault-resident plan has no pre-execution baseline/Git history, so checks 1/3/5
cannot establish historical checkbox transitions. Available checks flag missing
Stage 1 first-claim records, earlier Stage 3 proof fingerprints bound to prior
test trees, and Stage 2 commit-title matching advisories. These are retained as
final close-out proof/provenance debt; no fresh baseline is fabricated and no
whole-plan audit PASS is claimed. Earlier stage receipts remain historical
qualification evidence for their recorded revisions. The v4 lock and current
local checks above remain the current synthetic receipts. The native review
ledger reports zero agents started and never stopped. No owned tool is running.
