# global-security.md — format and input contract

`<vault>/Portfolio/global-security.md` is the portfolio-wide security dashboard: which projects
have open CRITICALs, which are trending the wrong way, which have never been audited. `portfolio
rebuild` regenerates it with `../scripts/security-scan.py | ../scripts/security-rollup.py`. **Never
edit it by hand.**

## Input contract — `security/history.jsonl`

A security-audit tool appends one JSON object per run to
`<vault>/Portfolio/<area>/<name>/security/history.jsonl`. That tool owns the format; this is the
consumer's view of it.

| Field | Required | Meaning |
|---|---|---|
| `run_id` | yes | `YYYYMMDD-HHMM` UTC; sorts chronologically |
| `mode` | yes | `full` \| `incremental` \| `feeds` |
| `started_at` / `finished_at` | no | ISO-8601 |
| `plugin_version` | no | |
| `counts` | no | open findings by severity |
| `deltas` | no | `new`/`regressed`/`reverified`/`carried`/`fixed`/`baseline_open`/`total_open`, plus `accepted` and `previously_accepted` |
| `lanes_ran` / `lanes_carried`, `cost` | no | |

Three rules this roll-up must never break:

1. **An optional field that is absent is `null`, never `0`.** "Not measured" and "measured
   zero" are different facts. The scan emits `null`; the render shows `?`. A dashboard that
   shows an unmeasured project as `0 CRITICAL` reports it as clean, which is the worst failure
   this file can have.
2. **`mode: "feeds"` means no code lane ran.** A feed-only run re-checks dependency advisories
   against unchanged code; its counts are carried forward, not re-verified. Such rows are marked
   `⚠` with a legend line, and are never presented as an audit.
3. **`total_open` already includes accepted findings.** "Open and not currently suppressed" is
   `total_open − accepted`. Never treat `accepted` as already subtracted.

Unknown keys and unknown `mode` values are passed through, not rejected: the producer is
maintained elsewhere and will add fields.

## Where the scan reads from

`security-scan.py` reads the plugin's vault and registry (`registry-format.md`), and refuses an
unset or unreachable vault and an unusable registry with a non-zero exit and no JSON. Two
environment overrides exist for tests, and its `--help` documents both: `PORTFOLIO_CONFIG` (a
YAML file holding `vault_dir` and optionally `registry`, outranking the plugin's configuration)
and `SECURITY_REGISTRY` (the registry file, outranking every other source).

## Rendering

The page opens with a summary line (audited projects, never audited, how many have open
CRITICALs and their total) and, when some audited project recorded no severity counts, a note
that `?` is not clean.

The main table has one row per audited project: last run id, age in days, mode, CRIT, HIGH,
Open, Accepted, trend. Rows are worst-first: open CRITICAL descending, then HIGH, then age. An
unknown count sorts as *worse* than a known zero, because unmeasured is not clean.

Further sections, each only when it has content: **Never audited** (enabled projects with no
history); **History problems** (malformed `history.jsonl` lines, skipped and counted); **Could
not assess** (a project whose scan raised; one broken project never aborts the sweep).

## Degradation

The layer is additive. If `security-scan.py` or `security-rollup.py` is missing, or either fails
or times out, or the roll-up prints no `# Global security` heading, `portfolio rebuild` prints
one status line, leaves any existing `global-security.md` **intact** (never truncated), and the
other roll-ups are byte-identical. Locked by `../tests/test-security-degradation.py`; the scan's
behaviour by `../tests/test-security-scan.py`.
