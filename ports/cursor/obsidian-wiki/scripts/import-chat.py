#!/usr/bin/env python3
"""Inventory an Element Matrix ZIP and optionally prepare safe revision artifacts.

Without output paths this command is read-only. A preparation run writes only
opaque revision metadata and a separately requested protected locator map; it
never extracts a ZIP member or writes to the general wiki.
"""
from __future__ import annotations

import argparse
import json
import sys

from matrix_chat_adapter import ArchiveError, build_records, canonical_json, write_immutable


def fail(message: str, as_json: bool) -> int:
    result = {"ok": False, "errors": [message]}
    print(json.dumps(result, sort_keys=True) if as_json else f"ERROR: {message}")
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("--source-id", default="mr-2024-2025")
    parser.add_argument("--archive-sha256")
    parser.add_argument("--revision-out", help="immutable safe revision JSON output")
    parser.add_argument("--events-out", help="immutable sanitized event JSONL output")
    parser.add_argument("--attachments-out", help="immutable safe attachment manifest output")
    parser.add_argument("--worklist-out", help="immutable safe coverage worklist output")
    parser.add_argument("--protected-map-out", help="protected companion locator-map output")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    artifact_paths = (args.revision_out, args.events_out, args.attachments_out, args.worklist_out, args.protected_map_out)
    if any(artifact_paths) and not all(artifact_paths):
        return fail("preparation requires revision, events, attachment, worklist, and protected-map outputs together", args.json)
    try:
        result = build_records(args.archive, args.source_id, args.archive_sha256)
        summary = result["summary"]
        if all(artifact_paths):
            written = {
                "revision": write_immutable(args.revision_out, canonical_json(result["revision"])),
                "events": write_immutable(args.events_out, b"".join(canonical_json(event) for event in result["revision"]["events"])),
                "attachments": write_immutable(args.attachments_out, canonical_json(result["attachments"])),
                "worklist": write_immutable(args.worklist_out, canonical_json(result["worklist"])),
                "protected_map": write_immutable(args.protected_map_out, canonical_json(result["protected_map"]), mode=0o600),
            }
            summary = {**summary, "prepared": written}
    except ArchiveError as exc:
        return fail(str(exc), args.json)
    print(json.dumps(summary, sort_keys=True) if args.json else f"events={summary['events']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
