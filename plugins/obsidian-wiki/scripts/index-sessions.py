#!/usr/bin/env python3
"""index-sessions.py — enumerate AI coding sessions across the five supported tools.

Why this exists
---------------
`scan-sessions` used to do discovery itself, which forced eight Bash grants into
its frontmatter — including `Bash(sqlite3:*)`, which the 2026-08-13 sec-audit
rated HIGH (CWE-78): the sqlite3 CLI's `.shell` / `.system` / `.load`
dot-commands execute arbitrary code, and a read-only database URI does not
disable them. Verified on this host. That grant sat on the one skill whose whole
job is parsing untrusted transcripts, which is the worst possible pairing.

Swapping sqlite3 for a `Bash(python3:*)` grant would have been theatre — python3
is a general interpreter too. So discovery moves out of the skill entirely: this
script runs from a hook (hooks are not governed by `allowed-tools`) and writes an
index the skill can simply Read.

Everything the storage-paths reference learned on 2026-08-13/14 is encoded here
deterministically rather than left to the agent to remember:

  * Codex rollouts carry `session_meta.originator` / `thread_source`; only
    `codex-tui` + `user` is an interactive session. On a measured week, 25 of 32
    rollouts were `codex_exec` automation or subagent threads.
  * Codex session ids are UUIDv7, so an 8-char prefix is a timestamp, not an
    identity — 32 rollouts yielded 29 unique prefixes. The full id is recorded.
  * Gemini keeps conversations under `~/.gemini/tmp/<project>/chats/`, NOT under
    `~/.gemini/history/`, which holds only `.project_root` markers.
  * OpenCode migrated from `storage/project/*.json` to a SQLite database; the
    old path still resolves and holds a stale project registry.

Reads only. Opens the OpenCode database read-only through the sqlite3 module,
so no CLI and no dot-commands are involved at any point.

Output: JSON to stdout, or to --out. Pure stdlib.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
import time

HOME = os.path.expanduser("~")

# Claude Code writes untimestamped header events (last-prompt, mode,
# permission-mode, bridge-session, file-history-snapshot) before the first real
# one, so the start date can sit several lines in. Bounded so a malformed or
# header-only transcript still costs O(1) rather than a full scan.
PREAMBLE_MAX_LINES = 50


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(epoch))


def _within(path: str, cutoff: float) -> bool:
    try:
        return os.path.getmtime(path) >= cutoff
    except OSError:
        return False


def _note(path, exc):
    """Record a per-file parse failure without crashing the run.

    A broad catch is the right shape here — this parses transcripts from five
    external tools and one malformed file must never sink the index — but
    swallowing silently hid which file failed. bandit B110 / ruff S110 flag the
    bare `pass`; the answer is to say something, not to narrow the catch.
    """
    sys.stderr.write(f"index-sessions: skipped {path}: {type(exc).__name__}\n")


SESSION_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def claude_code(cutoff):
    """Sessions live at projects/<encoded-cwd>/<session-uuid>.jsonl — exactly one
    level deep, named by UUID.

    Everything deeper is something else. `<project>/<uuid>/subagents/agent-*.jsonl`
    holds SUBAGENT transcripts, and there are far more of them than sessions: a
    30-day window here held 1071 subagent files against 464 real sessions. Walking
    them in would have filled the vault with dispatched-agent chatter — the same
    defect this indexer already filters for Codex (`thread_source: subagent`), so
    it is filtered here too rather than left for the caller to notice.
    """
    root = os.path.join(HOME, ".claude", "projects")
    out = []
    for dirpath, _d, files in os.walk(root):
        rel_depth = os.path.relpath(dirpath, root).count(os.sep)
        for fn in files:
            if not fn.endswith(".jsonl"):
                continue
            p = os.path.join(dirpath, fn)
            if not _within(p, cutoff):
                continue
            # depth 0 == directly under projects/<encoded-cwd>/
            if rel_depth != 0 or not SESSION_UUID_RE.match(fn[:-6]):
                continue
            # True start is the first event's timestamp; the file mtime is the
            # LAST write and drifts days past it on long-running sessions.
            start = None
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    for _ in range(PREAMBLE_MAX_LINES):
                        line = fh.readline()
                        if not line:
                            break
                        try:
                            ts = json.loads(line).get("timestamp")
                        except ValueError:  # one bad line, keep looking
                            continue
                        if ts:
                            start = ts[:10]
                            break
            except Exception as e:      # malformed transcript: fall back, do not crash
                _note(p, e)
            out.append({
                "tool": "claude-code", "path": p,
                "session_id": fn[:-6], "short_id": fn[:8],
                "date": start or _iso(os.path.getmtime(p)),
                "date_source": "first-event" if start else "mtime",
                "project": os.path.basename(dirpath),
                "size": os.path.getsize(p),
            })
    return out


def codex(cutoff):
    root = os.path.join(HOME, ".codex", "sessions")
    out = []
    for dirpath, _d, files in os.walk(root):
        for fn in sorted(files):
            if not (fn.startswith("rollout-") and fn.endswith(".jsonl")):
                continue
            p = os.path.join(dirpath, fn)
            if not _within(p, cutoff):
                continue
            meta = {}
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    meta = (json.loads(fh.readline()) or {}).get("payload") or {}
            except Exception as e:      # malformed transcript: fall back, do not crash
                _note(p, e)
            originator = meta.get("originator")
            thread_source = meta.get("thread_source")
            sid = meta.get("session_id") or ""
            out.append({
                "tool": "codex", "path": p,
                "session_id": sid,
                # UUIDv7: the first 8 chars are a timestamp and collide, so the
                # short id is recorded for naming but is NOT an identity.
                "short_id": sid[:8],
                "date": (meta.get("timestamp") or "")[:10] or _iso(os.path.getmtime(p)),
                "date_source": "session_meta" if meta.get("timestamp") else "mtime",
                "cwd": meta.get("cwd"),
                "originator": originator,
                "thread_source": thread_source,
                # The filter the skill must apply; computed here so it cannot be
                # forgotten. codex_exec runs and subagent threads are automation.
                "interactive": originator == "codex-tui" and thread_source == "user",
                "size": os.path.getsize(p),
            })
    return out


def cursor(cutoff):
    root = os.path.join(HOME, ".cursor", "projects")
    out = []
    for dirpath, _d, files in os.walk(root):
        if os.path.basename(os.path.dirname(dirpath)) != "agent-transcripts":
            continue
        for fn in files:
            if not fn.endswith(".jsonl"):
                continue
            p = os.path.join(dirpath, fn)
            if not _within(p, cutoff):
                continue
            parts = p.split(os.sep)
            project = parts[parts.index("projects") + 1] if "projects" in parts else None
            out.append({
                "tool": "cursor", "path": p,
                "session_id": fn[:-6], "short_id": fn[:8],
                # No in-event timestamps exist in a Cursor transcript.
                "date": _iso(os.path.getmtime(p)), "date_source": "mtime",
                "project": project,
                # UUIDs repeat across project contexts, so identity is the pair.
                "idempotency_key": f"{project}:{fn[:-6]}",
                "size": os.path.getsize(p),
            })
    return out


def gemini(cutoff):
    root = os.path.join(HOME, ".gemini", "tmp")
    out = []
    for dirpath, _d, files in os.walk(root):
        if os.path.basename(dirpath) != "chats":
            continue
        for fn in sorted(files):
            if not (fn.startswith("session-") and fn.endswith(".json")):
                continue
            p = os.path.join(dirpath, fn)
            if not _within(p, cutoff):
                continue
            sid = start = None
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    d = json.load(fh)
                sid = d.get("sessionId")
                start = (d.get("startTime") or "")[:10] or None
            except Exception as e:      # malformed transcript: fall back, do not crash
                _note(p, e)
            m = re.match(r"session-(\d{4}-\d{2}-\d{2})T[\d-]+-([0-9a-f]{8})", fn)
            out.append({
                "tool": "gemini", "path": p,
                "session_id": sid or (m.group(2) if m else fn),
                "short_id": (m.group(2) if m else (sid or "")[:8]),
                "date": start or (m.group(1) if m else _iso(os.path.getmtime(p))),
                "date_source": "startTime" if start else ("filename" if m else "mtime"),
                "project": os.path.basename(os.path.dirname(dirpath)),
                "size": os.path.getsize(p),
            })
    return out


def opencode(cutoff):
    """OpenCode migrated to SQLite; storage/project/*.json is a stale registry."""
    db = os.path.join(HOME, ".local", "share", "opencode", "opencode.db")
    if not os.path.exists(db):
        return []
    out = []
    try:
        # Read-only URI + the sqlite3 module: no CLI, so no dot-commands exist
        # to abuse. immutable=0 so a live WAL is still read correctly.
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id, title, directory, parent_id, time_created, time_updated "
            "FROM session WHERE time_updated >= ? ORDER BY time_updated DESC",
            (int(cutoff * 1000),)).fetchall()
        for r in rows:
            sid = r["id"] or ""
            out.append({
                "tool": "opencode", "path": db,
                "session_id": sid,
                # ses_-prefixed, not a UUID; strip the prefix for the short id.
                "short_id": sid[4:12] if sid.startswith("ses_") else sid[:8],
                "date": _iso((r["time_created"] or 0) / 1000),
                "date_source": "time_created",
                "title": r["title"], "directory": r["directory"],
                # A child session is a spawned thread, not a user session.
                "interactive": r["parent_id"] is None,
                "size": None,
            })
        con.close()
    except sqlite3.Error as e:
        sys.stderr.write(f"index-sessions: opencode read failed: {e}\n")
    return out


TOOLS = {"claude-code": claude_code, "codex": codex, "cursor": cursor,
         "gemini": gemini, "opencode": opencode}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--tool", action="append", choices=sorted(TOOLS))
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    cutoff = time.time() - a.days * 86400
    index = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "window_days": a.days, "tools": {}}
    for name in (a.tool or sorted(TOOLS)):
        try:
            found = TOOLS[name](cutoff)
        except Exception as e:                      # one tool must never sink the rest
            index["tools"][name] = {"error": str(e), "sessions": [], "total": 0}
            continue
        # "Nothing in the window" and "nowhere to look" are different answers and
        # must not render the same — the whole reason Gemini and OpenCode went
        # unnoticed for months.
        index["tools"][name] = {
            "sessions": sorted(found, key=lambda s: (s.get("date") or "", s.get("path") or "")),
            "total": len(found),
            "store_present": _store_present(name),
        }

    text = json.dumps(index, indent=1, sort_keys=True)
    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        # tempfile, not a PID suffix — a PID is predictable.
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(a.out), prefix=".sessions-index.")
        with os.fdopen(fd, "w") as fh:
            fh.write(text + "\n")
        os.replace(tmp, a.out)
    else:
        print(text)
    return 0


def _store_present(name):
    return {
        "claude-code": os.path.isdir(os.path.join(HOME, ".claude", "projects")),
        "codex": os.path.isdir(os.path.join(HOME, ".codex", "sessions")),
        "cursor": os.path.isdir(os.path.join(HOME, ".cursor", "projects")),
        "gemini": os.path.isdir(os.path.join(HOME, ".gemini", "tmp")),
        "opencode": os.path.exists(
            os.path.join(HOME, ".local", "share", "opencode", "opencode.db")),
    }[name]


if __name__ == "__main__":
    sys.exit(main())
