# Local SQLite wiki pilot status — 2026-10-11

Stage 3's model-free core is technically complete on synthetic evidence. Tasks
4.1–4.2 are implemented. Task 4.3, Task 4.4 and the final Stage 4 gate remain
incomplete. The configured Claude adapter remains unqualified after strict-request failures; the pilot remains
inactive. No real-wiki answer-model run or normal adoption was selected.

Branch: `feat/local-sqlite-wiki-pilot`; core gate `b20cfaa`, adapter `37e9929`,
packaging `78bb7b1`, initial acceptance runner `21ba7d4`. This progress change
records six further authorized client traces, provides the complete read-request
contract inline, and records fresh synthetic qualification and the blocker.
It is a partial Task 4.3 commit, not a green task or gate.

## Current local evidence

| Check | Actual result | Qualification scope |
| --- | --- | --- |
| Fresh independent v6 Recall@5 | 20/20; 5/5 each exact/conceptual/rationale/historical | Synthetic installed CLI; separate development topics |
| Exact path/title/alias resolution | 60/60 | Synthetic installed CLI |
| Read-bound citation occurrences | 50/50, including repeated citations | Structural provenance only |
| Absent/protected/ambiguous/contradictory/date/partial controls | 1/1 each | Model-free evidence behavior; actual answer handling unqualified |
| Warm search p95 | 0.068044 s | Host end-to-end CLI, including startup/scans/JSON |
| Cold unavailable status / refresh | 0.046781 / 0.067807 s | Synthetic host measurements |
| Peak child RSS | 21,676 KiB | Observed Linux RUSAGE_CHILDREN peak |
| Total state / maximum read response | 194,902 / 4,389 bytes | Below 128 MiB / 24,000-byte limits |
| Installed live CLI | PASS | Fresh fake lookup/get/verify, then revocation and old/buffered evidence refusal |
| Stage4IntegrationCases | 1/1 PASS; part of four fix-scope checks in 1.606 s | Installed key rotation/revocation, source preservation, disabled/admin separation |
| Full regression | 41/41 wrappers PASS; 78 pilot tests | Actual discovery runner; six integration cases; 53 Python sources syntax checked |
| Latest configured client traces | Status6/6, search/read1; 0/6 qualified; $0.4116868 | Actual configured Claude2.1.296 route; schema refusals, no native mode denial |
| Real-vault lookup / owner usefulness | Pending / pending | Runner implemented; representative current private workload not supplied/run |

Current lock SHA256: `ccd0388f816b5667fccf7dd7018ea3572c25688c2f53402a8f91c2a18ac7b6fd`.
Independent v6 manifest canonical hash:
`a35733a027b6c36d3b779ecd126f7e29c8445098d560e4a16cec5a368996ef91`.
The complete 36-file lock was validated before and after acceptance and final
checks. The original acceptance set and v2/v3/v4/v5 sets were each opened once; code
changes retired their implementation-specific receipts. None was rerun as an
independent quality claim. V6 was frozen after the inline contract and copied installed-flow test repair. Historical research holdouts remain untouched.

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
Those initial checks did not explain the denial. The subsequent diagnostic and
model-free native analysis below isolate a heredoc rejection; the replacement
input form still awaits actual client qualification.

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

## Authorized permission diagnostics and repair

The owner authorized exactly two additional fake-only diagnostic traces under an
estimated $0.25 total cap with possible overshoot. Both launches are consumed:

| Diagnostic | Cost USD | Seconds | Actual outcome |
|---|---:|---:|---|
| Packaged grant | 0.0451702 | 7.738 | One status call, native dontAsk denial |
| Session-only exact executable grant | 0.0182450 | 6.684 | One status call, native dontAsk denial |

Total $0.0634152, zero overshoot, unchanged fake-source inventory. Cumulative
recorded spend with the earlier six traces is $0.3466998. No successful status,
read or citation occurred. The literal session grant also failed, ruling out a
failure caused solely by expanding CLAUDE_PLUGIN_ROOT. No further paid launch is
authorized by unused dollars. The configured model/auth route was retained;
credentials were removed with the temporary configuration. No global edits,
model override, automatic retries or real-wiki model content were used.

Model-free analysis executes the installed Claude 2.1.296 embedded parser and
semantic analyzer on the recorded command. Its early brace-plus-quote check
classifies the quoted JSON heredoc as `too-complex`, reason `Contains brace with
quote character (expansion obfuscation)`, differential=true. The same executable
and JSON in a single-quoted here-string (`<<<`) classify as `simple`. All three
controls (recorded heredoc, bare executable, here-string) produce the expected
results with the environment-scrub predicate both false and true: six checks.
Logging was inert; the scrub predicate was parameterized. This executes the
native semantic path offline, not the entire client's permission pipeline.
Private receipts retain the installed binary/module/inspection hashes and exact
results; extracted client code stays outside Git and the vault.

The repair updates command instructions, client harness instructions and the
strict deny-only guard together. It permits one direct exact executable and one
single-quoted JSON here-string. Apostrophes encode as JSON \u0027; shell quote
breaks, extra arguments/operators, substitutions outside the literal payload,
heredocs and non-read operations refuse. Payload decoding now shares the CLI's
strict duplicate-key/size/constant checks. A real local Bash round-trip preserves
apostrophe, dollar/backtick/substitution text and creates no injection sentinel.
The guard still never approves permissions. No broad shell or interpreter grant
was introduced. Native syntax success does not establish actual client access.

Presence-shaped defect sweep: `rg -n 'heredoc|WIKI_REQUEST|<<.*REQUEST' plugins
 tests docs -g '*.py' -g '*.md'`. Current operational examples, guard and harness
are repaired; the remaining heredoc is an explicit rejection control and the
historical diagnostic description. Earlier opened acceptance sets are retired
on this implementation change; fresh independent qualification is required.

## Latest six-case qualification and inline contract repair

The owner authorized six fresh fake-only traces on6c12c66 under estimated$1
with possible overshoot,150seconds each,no automatic retries. All six launches
are consumed once, total$0.4116868, overshoot0, source inventory unchanged.
Observed duration11.444–29.277seconds. Packaged status succeeds6/6 with no native
mode denial. Contradiction also completes search and one authenticated read;
all remaining denials are the containment guard rejecting invalid request schemas.

| Case | Cost USD | Actual events and answer judgment |
|---|---:|---|
| exact | 0.0563204 | Status succeeds; resolve uses unsupported locator field; required instruction absent |
| alias | 0.0492352 | Status succeeds; resolve uses query/generation/limit instead of selector; required instruction absent |
| missing-protected | 0.0545156 | Status succeeds; both invalid resolves refused; no access code/canary, admission unexercised |
| date | 0.0551738 | Status succeeds; both invalid resolves refused; required dated observations absent |
| contradiction | 0.1484530 | Status/search/get succeed; verify citations omit page_id and refuse; required observations withheld |
| oversized | 0.0479888 | Status succeeds; invalid resolve refuses; over-budget omission unexercised, no cause invented |

Fresh independent default evaluator `/root/client_answer_judgment_v2`, briefed
only on goals/pass criteria/artifact locations, reads the actual six answers and
events against frozen labels: FAIL, two Blocking (answerable lookup and citation
completion), one Material (oversized omission unqualified). No displayed
citations or invented instruction/access-code/cause/canary occurred. Safe
withholding remains safety evidence, not useful answer qualification. All
processes exit0 while all six transport receipts fail. Receipt/manifest/launch
lock identities agree. This judgment covers6c12c66, not the repaired moving tree.

The shipped command supplied only a status request example and prose naming
other operations; the full strict schemas lived in operator documentation that
the Bash-only qualification surface did not expose. The repair makes every read
operation's actual schema directly available in the invoked command. It includes
all resolve selector kinds, the single generation-bound get, authentic receipt,
per-citation page_id, body UTF-8/exclusive offsets, response fields and strict
verification/refusal behavior. No request API, guard, grant, source authority or
model route is broadened. Do not attribute strict field validation to a remaining
native permission failure.

Absence-shaped defect invariant: every read operation in contracts.FIELDS has
an inline strict-schema-valid request example, and all path/title/alias modes
are covered. The new test first failed because all JSON request examples were
absent. It now executes each documented request through copied installed admin
and read artifacts in a complete build/status/resolve/search/get/verify flow.
Required boundary review found one Important evidence mismatch (initially the
test invoked repository binaries); copied installed execution fixes it. Final
review APPROVE0Critical/Important/Suggestions; AdapterCases3/3 PASS. Artifact
scope sweep: `rg -n 'ROOT.*wiki-access.py|def test.*installed|installed.*flow'
 tests/wiki_access_cases.py`; genuine installed receipts use copied packages.

Full regression at entry41/41 wrappers,78 pilot cases,53syntax sources and six
integration cases passes. Test-only installed-artifact correction then passes
four AdapterCases/Stage4Integration checks in1.606seconds; no overlapping mutation
or unreported full rerun is credited. Fresh independent-v6 recall20/20, exact60/60,
citations50/50 and six structural controls1/1; current36-file lock validates after
checks. Installed liveCLI PASS. First-claim mutation proof refreshed for the final
tree. Earlier opened sets retired without reuse. Current-model semantic support
and real-source/usefulness qualification stay separately pending.

Cumulative14 authorized launches cost$0.7583866: earlier six$0.2832846, two
diagnostics$0.0634152 and latest six$0.4116868. No launch is retried, no expense is
unknown and no unused dollars authorize another call. No real-wiki model content,
global edit, model override or adoption is selected.

## Resume dependency

The inline-contract repair and required boundary review are complete on fresh
synthetic evidence. Seek fresh authorization for six fake-only configured-client
traces on the reviewed repair (estimated$1 total, accepted possible overshoot,
150seconds each,no automatic retries,existing configured route). All14 earlier
launches remain consumed; leftover dollars grant no new launch. Packaged status
access is proved, while useful read/verified-answer completion remains unqualified
until actual current-client events and independent answer judgment pass. No
permission bypass or adoption is selected.

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
qualification evidence for their recorded revisions. The v6 lock and current
local checks above are the new synthetic receipts; earlier sets remain historical. The native review
ledger reports zero agents started and never stopped. No owned tool is running.
