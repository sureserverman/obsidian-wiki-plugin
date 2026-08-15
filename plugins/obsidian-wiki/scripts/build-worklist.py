#!/usr/bin/env python3
"""build-worklist.py — turn a session index into a pending-import worklist.

Why this exists
---------------
The first worklist was hand-built and deduped on the filename stem
`<tool>-<date>-<short_id>`, comparing the index's date against the dates of the
files already in `raw/sessions/`. That is the one comparison that cannot work:
`import-session` names a file from the session's **first-event** date, while the
index dated 224 of 606 rows from the file **mtime** — the last write, which on a
long session drifts days past the start. Every drifted session therefore looked
un-imported. 64 of that worklist's 606 "pending" rows were already in the vault
under a different date, and importing it would have written 64 duplicate pages.

So dedup here is on session **identity**, read from the extracts' own
frontmatter, and never on a date:

  * `source-uuid` — the session id, for every tool.
  * `source-project` as well, for Cursor only: Cursor reuses session UUIDs across
    project contexts, so `(project, uuid)` is the key and the UUID alone would
    false-dedup two genuinely different sessions.

Fixing the indexer's mtime fallback (see `index-sessions.py`) removed the drift
for Claude Code, but Cursor transcripts carry no in-event timestamps at all, so
their dates are mtime-derived by nature. Identity-based dedup is what makes the
worklist correct for Cursor regardless.

Reads only. Pure stdlib. Output: JSON to stdout, or to --out.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import tempfile


def imported_identities(raw_dir):
    """Identity keys for every extract already in raw/sessions/.

    Returns (by_uuid, by_uuid_project). Frontmatter is read line-wise rather
    than with a YAML parser — stdlib only, and the fields are flat scalars.
    """
    by_uuid, by_uuid_project = set(), set()
    try:
        names = os.listdir(raw_dir)
    except OSError as e:
        sys.stderr.write(f"build-worklist: cannot read {raw_dir}: {e}\n")
        return by_uuid, by_uuid_project

    for fn in names:
        if not fn.endswith(".md"):
            continue
        tool = uuid = project = None
        try:
            with open(os.path.join(raw_dir, fn), encoding="utf-8", errors="replace") as fh:
                if fh.readline().strip() != "---":       # no frontmatter block
                    continue
                for line in fh:
                    if line.strip() == "---":
                        break
                    key, _, val = line.partition(":")
                    val = val.strip()
                    if key == "source-tool":
                        tool = val
                    elif key == "source-uuid":
                        uuid = val
                    elif key == "source-project":
                        project = val
        except OSError:                                   # unreadable extract
            continue
        if tool and uuid:
            by_uuid.add((tool, uuid))
            by_uuid_project.add((tool, uuid, project))
    return by_uuid, by_uuid_project


def build(index, raw_dir):
    by_uuid, by_uuid_project = imported_identities(raw_dir)
    pending, dropped = [], collections.Counter()

    for tool, block in index["tools"].items():
        for r in block.get("sessions", []):
            # Codex writes a rollout for every run and only codex-tui + user is a
            # session; OpenCode child threads carry a parent_id. The indexer has
            # already decided this — `interactive` is absent for tools where the
            # question does not arise.
            if r.get("interactive") is False:
                dropped["non-interactive"] += 1
                continue
            sid = r.get("session_id") or r.get("short_id")
            if tool == "cursor":
                if (tool, sid, r.get("project")) in by_uuid_project:
                    dropped["already-imported"] += 1
                    continue
            elif (tool, sid) in by_uuid:
                dropped["already-imported"] += 1
                continue
            pending.append({
                "date": r["date"], "date_source": r["date_source"],
                "path": r["path"], "project": r.get("project"),
                "session_id": sid, "short_id": r["short_id"],
                "size": r.get("size"), "tool": tool,
                "stem": f"{tool}-{r['date']}-{r['short_id']}",
            })

    pending.sort(key=lambda r: (r["date"], r["tool"], r["short_id"]), reverse=True)
    return {
        "generated_from": index.get("generated_at"),
        "window_days": index.get("window_days"),
        "already_imported": len(by_uuid),
        "dedup_key": ("source-uuid frontmatter, plus source-project for cursor; "
                      "never the filename date"),
        "dropped": dict(dropped),
        "pending": len(pending),
        "sessions": pending,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--index", required=True, help="sessions-index.json from index-sessions.py")
    ap.add_argument("--raw", required=True, help="<vault>/raw/sessions directory")
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    with open(a.index, encoding="utf-8") as fh:
        index = json.load(fh)

    text = json.dumps(build(index, a.raw), indent=1, sort_keys=True)
    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        # tempfile, not a PID suffix — a PID is predictable.
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(a.out), prefix=".worklist.")
        with os.fdopen(fd, "w") as fh:
            fh.write(text + "\n")
        os.replace(tmp, a.out)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
