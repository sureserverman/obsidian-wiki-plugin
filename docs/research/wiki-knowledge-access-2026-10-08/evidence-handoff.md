# Evidence handoff — 2026-10-08

Recommendation and solution-shaping deliverables are complete; Stage 4 technical closure is pending its scoped client citation gate and review dispositions. Stages 1–3 are green. No architecture, deployment or production integration is approved. [Recommendation](./recommendation.md), [solution brief](./solution-brief.md), [comparison](./heldout-client-results.md).

Private evidence manifest SHA256: `1dbbc99065867e97b3f28ea61d1839d0ce4486658a2d3f75b3e07468c9b06c84`. It enumerates 7,290 files/symlinks and 3,718,828,171 regular-file bytes, with per-file hashes and private-source/private-research/public-third-party classification. Explicitly excluded mutable packaging/status metadata and regenerable bytecode are separate from the frozen evidence set. The archive also snapshots current packaging metadata; its own SHA256 receipt covers complete tar bytes.

Active pack: `/tmp/wiki-access-research-20261008-dan2ccod`, mode 0700. Durable private archive: `/home/user/.local/share/obsidian-wiki-research/2026-10-08/wiki-access-evidence.tar`, mode 0600 in a mode-0700 directory. `package-receipt.json` records archive, manifest and canonical-summary hashes. Tar member hashes are checked against the manifest without extraction or symlink dereferencing. No private corpus, query/label, source locator, native cache, raw answer or security-report body enters Git or the canonical summary.

The pack includes requirements; eligible source projections and manifest; topic-separated labels; original/fresh baseline and real-client read-cap receipts; pinned engines/models/dependencies; common guarded adapters; valid/failed/resource-refused runs; context ablations and immutable finalist lock; holdout ordering/results; lifecycle fixtures/native retention observations; actual fake-only MCP/client traces; corrected section/term audit and additive lock errata; decision claims, validations and pending actions. Original and repaired artifacts retain explicit lineage. Source labels and selected engine/configuration are unchanged after holdout opening.

Reproduction, using the active pack and original authorized source generation:

```
python3 /tmp/wiki-access-research-20261008-dan2ccod/harness.py validate --stage decision
python3 /tmp/wiki-access-research-20261008-dan2ccod/harness.py reproduce --query-id rust-exact --arm B
```

The scoped reproduction already matches search/full-page read and returns 2 with cited-answer trace BLOCKED. It requires an actual authorized configured-client receipt bound to that exact frozen query; unrelated synthetic answers cannot pass it. The prepared `heldout-client-plan.json` allows one future configured-Claude call only after content authorization: maximum $0.40, 150 s, five locked full pages totaling 23,397 bytes, no protected originals, no model override or global configuration changes, no automatic retry/tuning.

`RETENTION.md` explains hash verification, safe restoration and local retention. The pack contains intentionally adversarial fake symlinks. No target is followed while packaging. Absolute configuration/model/cache paths and original source hashes constrain live reproduction; archive relocation and other-host execution remain unproved. Drift must fail closed, not lead to rewritten locks or benchmark reruns.

Retain the durable local archive and active directory through owner acceptance and architecture selection. No automatic cleanup occurs. The owner must choose retention, managed private backup and any later deletion; filesystem permissions do not prove encrypted backup or secure erasure. Cleanup must never touch the shared source vault.

Remaining dispositions: real-wiki cited-answer binding BLOCKED on content route; owner usefulness and long-term retention ACTION NEEDED; other-host/client proof BLOCKED; a fresh owner-supplied synthesis/language workload PROPOSED. A new architecture/implementation plan follows owner selection. DEC-001/002/003 and GDEC-SEC-001 remain binding. Transport, technical research completion, product usefulness and production readiness are distinct.
