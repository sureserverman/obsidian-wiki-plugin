---
name: wiki-review-chat
description: Review an exact Matrix conversation batch before an accepted manual apply.
---

# Matrix conversation review

Inspect every proposed patch, coverage disposition, conflict, attachment review state,
and privacy finding. Apply only the reviewed digest with `apply-chat.py` during an
owner-confirmed exclusive maintenance window. Set the capability only in
`OBSIDIAN_WIKI_MAINTENANCE_TOKEN`; never put it in a page, log, preview, or prompt.

If a journal is incomplete, recover it before retrying. A changed base hash or foreign
maintenance owner is a conflict, not permission to overwrite.
