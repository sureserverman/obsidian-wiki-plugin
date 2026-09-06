#!/usr/bin/env python3
"""Validate version-1 Matrix conversation records without interpreting chat text."""
import argparse
import json
import re
import sys
from pathlib import Path

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EVENT_KINDS = {"message", "attachment", "state", "call", "encrypted-unavailable", "redaction", "edit"}
AVAILABILITY = {"available", "unavailable", "redacted", "disputed"}


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), []
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"cannot read JSON: {exc}"]


def validate_revision(record):
    errors = []
    if not isinstance(record, dict):
        return ["revision must be a JSON object"]
    for field in ("schema_version", "source_id", "archive_sha256", "revision_id", "events"):
        if field not in record:
            errors.append(f"missing required field: {field}")
    if record.get("schema_version") != 1:
        errors.append("unsupported schema_version")
    if not isinstance(record.get("source_id"), str) or not record.get("source_id"):
        errors.append("source_id must be a nonempty string")
    if not isinstance(record.get("archive_sha256"), str) or not SHA256_RE.fullmatch(record.get("archive_sha256", "")):
        errors.append("archive_sha256 must be 64 lowercase hex characters")
    events = record.get("events")
    if not isinstance(events, list):
        errors.append("events must be an array")
        return errors
    seen = set()
    for index, event in enumerate(events):
        prefix = f"events[{index}]"
        if not isinstance(event, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field in ("event_key", "occurred_at", "kind", "availability", "protected_locator_ref"):
            if not isinstance(event.get(field), str) or not event[field]:
                errors.append(f"{prefix} missing nonempty {field}")
        key = event.get("event_key")
        if isinstance(key, str):
            if key in seen:
                errors.append(f"{prefix} duplicates event_key")
            seen.add(key)
        if event.get("kind") not in EVENT_KINDS:
            errors.append(f"{prefix} unsupported kind: {event.get('kind')}")
        if event.get("availability") not in AVAILABILITY:
            errors.append(f"{prefix} unsupported availability: {event.get('availability')}")
    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate Matrix conversation revision, batch, or migration JSON.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--revision")
    group.add_argument("--batch")
    group.add_argument("--migration")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    mode, path = next((name, value) for name, value in (("revision", args.revision), ("batch", args.batch), ("migration", args.migration)) if value)
    record, errors = load_json(path)
    if not errors and mode == "revision":
        errors = validate_revision(record)
    elif not errors and not isinstance(record, dict):
        errors = [f"{mode} must be a JSON object"]
    verdict = {"ok": not errors, "mode": mode, "errors": errors}
    if args.json:
        print(json.dumps(verdict, sort_keys=True))
    else:
        print("OK" if verdict["ok"] else "ERROR: " + "; ".join(errors))
    return 0 if verdict["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
