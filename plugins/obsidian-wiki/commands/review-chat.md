---
description: Review a prepared Matrix conversation batch before an explicitly accepted apply
---

`review-chat` presents a batch's proposed patches, conflicts, exclusions, unavailable
events, disputed attachments, privacy findings, and exact digest. It distinguishes
participant reports, failed attempts, hypotheses, proposals, and externally verified
claims.

It never applies a batch by elapsed time, filename, or a prior unrelated approval. An
apply may proceed only when the owner accepts this exact digest and every target base
hash still matches.
