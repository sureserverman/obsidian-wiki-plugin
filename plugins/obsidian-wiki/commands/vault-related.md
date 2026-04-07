---
description: Find missing cross-references for a specific vault page
---

Use the `vault-related` skill to find pages in `~/dev/knowledge` that the target page
should link to but doesn't.

Target page: $ARGUMENTS

If `$ARGUMENTS` is empty, ask which page to analyze. The skill is read-only by
default — it suggests cross-refs and waits for confirmation before applying any edit.
