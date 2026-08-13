#!/usr/bin/env python3
"""score-session.py — score a Claude Code session JSONL for vault-worthiness.

Stream-friendly heuristic scorer used by capture-session.sh. Reads a session
transcript at the path given as argv[1] and prints a single line of the form:

    <score>|<turn_count>|<topic>|<errors>

to stdout, where:
  - score:      integer in approximately [-3, 5]; capture threshold is 2
  - turn_count: line count of the JSONL (proxy for total events)
  - topic:      first user prompt sanitized to a single line, ≤60 chars
  - errors:     count of `"is_error":true` events (tool failure signal)

Claude Code only. Given a Codex rollout, a Cursor transcript, or any other
tool's session it exits 2 with a message on stderr and prints nothing — those
shapes parse as JSON but carry no roles, text or error markers here, so scoring
them would emit a confident, meaningless number. Cross-tool scoring lives in
the scan-sessions skill (Step 4), which samples and judges instead.

Signals (mirrors scan-sessions SKILL.md, simplified to what a hook can
compute without vault context):

  +1  long session         turn_count > 50
  +2  error cluster        ≥ 3 tool errors
  +1  substantive end      final assistant message > 800 chars
  +1  user satisfaction    "perfect" / "thanks" / "works" / "got it" near end
  -2  routine fix          "typo" / "rename" / "format" in early prompts
  -1  gave up              "nevermind" / "give up" / "forget it" near end

Reads the whole file (session JSONLs are typically << 10MB). For huge files
the head/tail-only signals would be the same; the errors count would lose
mid-session errors but those are exactly the signal we want, so a full scan
is fine.

Pure stdlib. No third-party deps.
"""

from __future__ import annotations

import json
import re
import sys

HEAD = 30
TAIL = 30


def text_of(obj: object) -> str:
    """Extract concatenated text from a Claude Code JSONL event."""
    if not isinstance(obj, dict):
        return ""
    msg = obj.get("message")
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                t = c.get("text", "")
                if isinstance(t, str):
                    parts.append(t)
        return " ".join(parts)
    return ""


def role_of(obj: object) -> str:
    if not isinstance(obj, dict):
        return ""
    msg = obj.get("message")
    if isinstance(msg, dict):
        r = msg.get("role")
        if isinstance(r, str) and r:
            return r
    t = obj.get("type")
    return t if isinstance(t, str) else ""


def parse_line(line: bytes) -> object:
    try:
        return json.loads(line)
    except Exception:
        return None


CC_EVENT_TYPES = {"user", "assistant", "summary", "system"}


def looks_like_claude_code(lines: list[bytes]) -> bool | None:
    """Does this transcript use the Claude Code event shape?

    Returns True/False, or None when the sample carried no parseable JSON at
    all (empty or non-JSONL file) — the caller keeps its legacy behavior there
    rather than blaming the tool.

    The signals every Claude Code event carries and no other supported tool
    does: a `message` object with a `role`, or a top-level `type` naming a
    transcript event. Codex nests everything under `payload`; Cursor puts
    `role` at the top level with no `type`. Both parse fine as JSON and then
    yield no text, no roles and no errors — which scores as a flat, meaningless
    number instead of failing. Hence this check.
    """
    parsed = 0
    for line in lines[:50]:
        obj = parse_line(line)
        if not isinstance(obj, dict):
            continue
        parsed += 1
        msg = obj.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("role"), str):
            return True
        if obj.get("type") in CC_EVENT_TYPES:
            return True
    return None if parsed == 0 else False


def main() -> int:
    if len(sys.argv) < 2:
        print("0|0||0")
        return 0

    path = sys.argv[1]
    try:
        with open(path, "rb") as f:
            lines = f.readlines()
    except OSError:
        print("0|0||0")
        return 0

    turn_count = len(lines)

    # Refuse other tools' transcripts rather than scoring them to a flat
    # number. capture-session.sh treats a nonzero exit as "skip this
    # session", so this can only ever suppress a capture, never crash a hook.
    if looks_like_claude_code(lines) is False:
        print(
            f"score-session.py: {path} is not a Claude Code transcript "
            "(no message.role, no transcript event type). This scorer parses "
            "the Claude Code shape only — score Codex/Cursor/Gemini/OpenCode "
            "sessions with the scan-sessions Step 4 signals instead.",
            file=sys.stderr,
        )
        return 2

    first_user = ""
    final_assistant = ""
    head_blob_parts: list[str] = []
    tail_blob_parts: list[str] = []

    for line in lines[:HEAD]:
        obj = parse_line(line)
        if obj is None:
            continue
        t = text_of(obj)
        if not first_user and role_of(obj) == "user" and t:
            first_user = t
        if t:
            head_blob_parts.append(t.lower())

    # Walk the tail in order so the *last* assistant message wins.
    for line in lines[-TAIL:]:
        obj = parse_line(line)
        if obj is None:
            continue
        t = text_of(obj)
        if role_of(obj) == "assistant" and t:
            final_assistant = t
        if t:
            tail_blob_parts.append(t.lower())

    errors = 0
    for line in lines:
        # Cheap byte-level check — avoids JSON-parsing every line just to
        # find error markers. Both spaced and unspaced forms are seen in
        # practice across Claude Code versions.
        if b'"is_error":true' in line or b'"is_error": true' in line:
            errors += 1

    head_blob = " ".join(head_blob_parts)
    tail_blob = " ".join(tail_blob_parts)

    score = 0
    if turn_count > 50:
        score += 1
    if errors >= 3:
        score += 2
    if len(final_assistant) > 800:
        score += 1
    if re.search(r"\b(perfect|thanks|works|got it|exactly|nice work|great)\b", tail_blob):
        score += 1
    if re.search(r"\b(typo|rename|format|whitespace|reword)\b", head_blob):
        score -= 2
    # Use `.` for the apostrophe so the regex stays single-quote-friendly
    # for the bash hook that calls this script.
    if re.search(r"(nevermind|never mind|give up|forget it|doesn.t matter)", tail_blob):
        score -= 1

    topic = re.sub(r"\s+", " ", first_user).strip()
    # Strip pipes (our output delimiter) and trim length
    topic = topic.replace("|", "/")[:60]

    print(f"{score}|{turn_count}|{topic}|{errors}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
