---
description: Find content gaps (entities mentioned across pages with no dedicated page)
---

Use the `vault-gaps` skill to scan `~/dev/knowledge` for entities mentioned across
multiple pages that don't have a dedicated page yet.

This is read-only — it surfaces gap candidates. To actually fill a gap, drop a source
in `raw/` and run `/vault-ingest`.

If `$ARGUMENTS` is a number, use it as the minimum mention count for the high-confidence
section (default: 3).
