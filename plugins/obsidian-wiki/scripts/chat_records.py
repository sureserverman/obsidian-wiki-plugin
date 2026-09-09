"""Version-1 Matrix conversation record builders used by deterministic fixtures."""
import hashlib


def opaque_key(prefix, value):
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:16]}"


def event(event_id, occurred_at, kind="message", availability="available"):
    return {"event_key": opaque_key("ev", event_id), "occurred_at": occurred_at,
            "kind": kind, "availability": availability,
            "protected_locator_ref": opaque_key("pl", event_id)}


def revision(source_id, archive_sha256, revision_id, events):
    return {"schema_version": 1, "source_id": source_id,
            "archive_sha256": archive_sha256, "revision_id": revision_id,
            "events": events}
