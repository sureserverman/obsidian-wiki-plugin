#!/usr/bin/env python3
"""Mechanical triage of the pending-import worklist.

This is a QUEUE ORDER, not a vault-worthiness verdict. Every signal here is
counted from the transcript; none is inferred. Where a signal cannot be measured
for a tool, it is recorded as null rather than guessed — the failure mode this
whole exercise documented is agents inventing scores from whatever number was
lying around (file size, loose `Error:` greps, `lastPrompt` metadata counts).

Signals, per tool:
  prompts   claude-code only — `user` events whose content carries no tool_result
            block. The count of times a human actually typed something.
  errors    claude-code only — `"is_error":true`. Real failed tool calls. NOT a
            grep for the word "error", which matches ordinary prose.
  events    every tool — transcript lines (JSONL) or messages (Gemini JSON).
  size      every tool — bytes.

Tiering is deliberately coarse and states its own basis, so a reader can tell
what it does and does not know.
"""
import json, os, sys, collections

CC_ERR = b'"is_error":true'


def measure(row):
    p, tool = row["path"], row["tool"]
    out = {"events": None, "prompts": None, "errors": None}
    try:
        if tool == "claude-code":
            prompts = errors = events = 0
            with open(p, "rb") as fh:
                for raw in fh:
                    events += 1
                    if CC_ERR in raw:
                        errors += 1
                    if b'"type":"user"' not in raw:
                        continue
                    try:
                        e = json.loads(raw)
                    except ValueError:
                        continue
                    if e.get("type") != "user":
                        continue
                    c = e.get("message", {}).get("content")
                    if isinstance(c, list) and any(
                            isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                        continue
                    prompts += 1
            out.update(events=events, prompts=prompts, errors=errors)
        elif tool in ("codex", "cursor", "opencode"):
            with open(p, "rb") as fh:
                out["events"] = sum(1 for _ in fh)
    except OSError:
        pass
    return out


def tier(r):
    """Coarse buckets. Stated basis, no hidden arithmetic."""
    sz, ev, pr, er = r["size"] or 0, r["events"] or 0, r["prompts"], r["errors"]
    if sz < 20_000:
        return "C-trivial", "under 20 KB"
    if r["tool"] == "claude-code":
        if er and er >= 5 and pr and pr >= 3:
            return "A-debugging", f"{er} real tool errors across {pr} human prompts"
        if pr and pr >= 8:
            return "A-directed", f"{pr} human prompts — a steered session, not a one-shot"
        if er and er >= 5:
            return "B-errors", f"{er} real tool errors but only {pr} human prompts"
        if ev >= 400:
            return "B-long", f"{ev} events, {pr} human prompts, {er} errors"
        return "C-routine", f"{ev} events, {pr} human prompts, {er} errors"
    # No comparable per-event signal exists for these tools; rank on bulk only
    # and say so rather than inventing one.
    if ev >= 200:
        return "B-bulk", f"{ev} events (no error/prompt signal available for {r['tool']})"
    return "C-routine", f"{ev} events (no error/prompt signal available for {r['tool']})"


def main(worklist, out_path):
    rows = json.load(open(worklist))["sessions"]
    for i, r in enumerate(rows, 1):
        r.update(measure(r))
        t, why = tier(r)
        r["tier"], r["tier_basis"] = t, why
        if i % 100 == 0:
            print(f"  measured {i}/{len(rows)}", file=sys.stderr)

    order = {"A-debugging": 0, "A-directed": 1, "B-errors": 2, "B-long": 3,
             "B-bulk": 4, "C-routine": 5, "C-trivial": 6}
    rows.sort(key=lambda r: (order[r["tier"]], -(r["errors"] or 0),
                             -(r["prompts"] or 0), -(r["size"] or 0)))
    tally = collections.Counter(r["tier"] for r in rows)
    doc = {
        "generated": "2026-08-15",
        "basis": ("mechanical triage; queue order, not a worthiness verdict. "
                  "prompts/errors are claude-code only and are counted, never inferred. "
                  "errors = '\"is_error\":true', not a grep for the word error."),
        "tally": dict(tally),
        "sessions": rows,
    }
    with open(out_path, "w") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    print(json.dumps(dict(tally), indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
