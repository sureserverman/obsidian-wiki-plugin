#!/usr/bin/env python3
"""Validate version-1 Matrix conversation records without interpreting chat text."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EVENT_KINDS = {"message", "attachment", "state", "call", "encrypted-unavailable", "redaction", "edit"}
AVAILABILITY = {"available", "unavailable", "redacted", "disputed"}
REVIEW_STATES = {"approved", "excluded", "protected-only", "unavailable", "disputed", "pending"}


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


def safe_path(value):
    return isinstance(value, str) and value and not value.startswith("/") and "\\" not in value and "/../" not in f"/{value}" and not value.startswith("../")


def canonical_batch_digest(record):
    material = {key: value for key, value in record.items()
                if key not in {"digest", "accepted_digest", "apply_authorized"}}
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_batch(record):
    errors = []
    if not isinstance(record, dict):
        return ["batch must be a JSON object"]
    for field in ("schema_version", "batch_id", "digest", "source_id", "revision_id", "coverage", "claims", "attachments", "index_status", "changes"):
        if field not in record:
            errors.append(f"missing required field: {field}")
    if record.get("schema_version") != 1:
        errors.append("unsupported batch schema_version")
    if not isinstance(record.get("batch_id"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", record.get("batch_id", "")):
        errors.append("batch_id must be a safe identifier")
    for field in ("source_id", "revision_id"):
        if not isinstance(record.get(field), str) or not record[field]:
            errors.append(f"{field} must be a nonempty string")
    if not isinstance(record.get("digest"), str) or not SHA256_RE.fullmatch(record.get("digest", "")):
        errors.append("digest must be 64 lowercase hex characters")
    elif record["digest"] != canonical_batch_digest(record):
        errors.append("digest does not match the exact batch")
    changes = record.get("changes")
    if not isinstance(changes, list) or not changes:
        errors.append("changes must be a nonempty array")
        return errors
    paths = set()
    for index, change in enumerate(changes):
        prefix = f"changes[{index}]"
        if not isinstance(change, dict):
            errors.append(f"{prefix} must be an object")
            continue
        path = change.get("path")
        if not safe_path(path):
            errors.append(f"{prefix} has unsafe path")
        elif path in paths:
            errors.append(f"{prefix} duplicates path")
        else:
            paths.add(path)
        before = change.get("before_sha256")
        if before is not None and (not isinstance(before, str) or not SHA256_RE.fullmatch(before)):
            errors.append(f"{prefix} has invalid before_sha256")
        if not isinstance(change.get("content"), str):
            errors.append(f"{prefix} content must be text")
    coverage = record.get("coverage")
    if not isinstance(coverage, dict) or any(not isinstance(coverage.get(field), int) or coverage[field] < 0 for field in ("total_units", "accounted_units")):
        errors.append("coverage must provide nonnegative total_units and accounted_units")
    elif coverage["accounted_units"] != coverage["total_units"]:
        errors.append("coverage is not fully accounted")
    claims = record.get("claims")
    if not isinstance(claims, list):
        errors.append("claims must be an array")
    else:
        claim_ids = set()
        for index, claim in enumerate(claims):
            prefix = f"claims[{index}]"
            if not isinstance(claim, dict):
                errors.append(f"{prefix} must be an object")
                continue
            claim_id = claim.get("claim_id")
            if not isinstance(claim_id, str) or not claim_id:
                errors.append(f"{prefix} missing claim_id")
            elif claim_id in claim_ids:
                errors.append(f"{prefix} duplicates claim_id")
            else:
                claim_ids.add(claim_id)
            evidence = claim.get("evidence_keys")
            if not isinstance(evidence, list) or not evidence or any(not isinstance(key, str) or not key.startswith("ev_") for key in evidence):
                errors.append(f"{prefix} has no safe evidence_keys")
            destinations = claim.get("destinations")
            if not isinstance(destinations, list) or not destinations or any(path not in paths for path in destinations):
                errors.append(f"{prefix} destinations must be changed batch paths")
    attachments = record.get("attachments")
    if not isinstance(attachments, list):
        errors.append("attachments must be an array")
    else:
        for index, attachment in enumerate(attachments):
            prefix = f"attachments[{index}]"
            if not isinstance(attachment, dict) or not isinstance(attachment.get("attachment_key"), str) or not attachment["attachment_key"]:
                errors.append(f"{prefix} missing attachment_key")
            elif attachment.get("review_state") not in REVIEW_STATES:
                errors.append(f"{prefix} has unsupported review_state")
    if record.get("index_status") not in {"unchanged", "rebuilt"}:
        errors.append("index_status must be unchanged or rebuilt")
    return errors


def validate_migration(record):
    errors = []
    if not isinstance(record, dict):
        return ["migration must be a JSON object"]
    for field in ("schema_version", "migration_id", "snapshot_id", "changes"):
        if field not in record:
            errors.append(f"missing required field: {field}")
    if record.get("schema_version") != 1:
        errors.append("unsupported migration schema_version")
    for field in ("migration_id", "snapshot_id"):
        if not isinstance(record.get(field), str) or not record[field]:
            errors.append(f"{field} must be a nonempty string")
    changes = record.get("changes")
    if not isinstance(changes, list):
        errors.append("changes must be an array")
        return errors
    paths = set()
    for index, change in enumerate(changes):
        prefix = f"changes[{index}]"
        if not isinstance(change, dict):
            errors.append(f"{prefix} must be an object")
            continue
        path = change.get("path")
        if not safe_path(path):
            errors.append(f"{prefix} has unsafe path")
        elif path in paths:
            errors.append(f"{prefix} duplicates path")
        else:
            paths.add(path)
        for field in ("before_sha256", "after_sha256"):
            value = change.get(field)
            if value is not None and (not isinstance(value, str) or not SHA256_RE.fullmatch(value)):
                errors.append(f"{prefix} has invalid {field}")
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
    if not errors:
        validators = {"revision": validate_revision, "batch": validate_batch, "migration": validate_migration}
        errors = validators[mode](record)
    verdict = {"ok": not errors, "mode": mode, "errors": errors}
    if args.json:
        print(json.dumps(verdict, sort_keys=True))
    else:
        print("OK" if verdict["ok"] else "ERROR: " + "; ".join(errors))
    return 0 if verdict["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
