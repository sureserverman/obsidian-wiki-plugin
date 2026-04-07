---
description: Find content gaps (entities mentioned across pages with no dedicated page)
---

Use the `vault-gaps` skill to scan `~/dev/knowledge` for entities mentioned across
multiple pages that don't have a dedicated page yet.

**Arguments**: `$ARGUMENTS` — minimum mention count for the high-confidence section
(default: `3`).

If `$ARGUMENTS` is empty, use the default threshold. This is a **read-only** command;
to fill a gap, drop a source in `~/dev/knowledge/raw/` and run `/obsidian-wiki:ingest`.

**Examples**:
- `/obsidian-wiki:gaps` — entities mentioned by ≥3 pages
- `/obsidian-wiki:gaps 2` — lower the threshold to ≥2 pages
