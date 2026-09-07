"""Deterministic, privacy-bounded adapter for Element Matrix ZIP exports.

The adapter never extracts archive members.  Its public revision contains only
opaque identifiers and event metadata.  The caller must keep the returned
locator map in a protected companion store outside normal vault discovery.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import PurePosixPath
import stat
import tempfile
from typing import Any
import zipfile


PARSER_VERSION = "element-zip-v1"
MAX_MEMBERS = 10_000
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200


class ArchiveError(ValueError):
    """The archive cannot safely be treated as the supported Element shape."""


def opaque_key(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"


def sha256_path(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def safe_member_name(name: str) -> str:
    if not name or "\\" in name or name.startswith("/"):
        raise ArchiveError("unsafe member path")
    normalized = PurePosixPath(name)
    if any(part in {"", ".", ".."} for part in normalized.parts):
        raise ArchiveError("unsafe member path")
    return normalized.as_posix()


def archive_members(archive: zipfile.ZipFile) -> tuple[list[zipfile.ZipInfo], zipfile.ZipInfo, str, int]:
    infos = archive.infolist()
    if not infos or len(infos) > MAX_MEMBERS:
        raise ArchiveError("archive has an unsupported member count")
    names: set[str] = set()
    total = 0
    files: list[zipfile.ZipInfo] = []
    for info in infos:
        name = safe_member_name(info.filename)
        if name in names:
            raise ArchiveError("archive has duplicate normalized member names")
        names.add(name)
        mode = (info.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK:
            raise ArchiveError("archive contains a symbolic-link member")
        if info.is_dir():
            continue
        if info.file_size > MAX_MEMBER_BYTES:
            raise ArchiveError("archive member exceeds size limit")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise ArchiveError("archive exceeds expanded-size limit")
        if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise ArchiveError("archive member exceeds compression-ratio limit")
        files.append(info)
    exports = [info for info in files if PurePosixPath(info.filename).name == "export.json"]
    if len(exports) != 1:
        raise ArchiveError("archive must contain exactly one export.json")
    export = exports[0]
    root = PurePosixPath(export.filename).parent.as_posix()
    prefix = "" if root == "." else root + "/"
    if any(prefix and not safe_member_name(info.filename).startswith(prefix) for info in files):
        raise ArchiveError("archive has ambiguous export roots")
    return files, export, root, len(infos)


def load_element_export(path: str) -> tuple[dict[str, Any], list[zipfile.ZipInfo], str, int]:
    try:
        with zipfile.ZipFile(path) as archive:
            files, export_info, root, member_count = archive_members(archive)
            with archive.open(export_info) as handle:
                payload = handle.read(MAX_MEMBER_BYTES + 1)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ArchiveError("unsupported archive") from exc
    if len(payload) > MAX_MEMBER_BYTES:
        raise ArchiveError("export.json exceeds size limit")
    try:
        record = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArchiveError("export.json is not valid UTF-8 JSON") from exc
    if not isinstance(record, dict) or not isinstance(record.get("messages"), list):
        raise ArchiveError("unsupported Element export shape")
    return record, files, root, member_count


def timestamp(value: Any) -> str:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ArchiveError("event has invalid origin_server_ts")
    return dt.datetime.fromtimestamp(value / 1000, tz=dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def event_kind(event: dict[str, Any], content: dict[str, Any]) -> tuple[str, str]:
    event_type = event["type"]
    if event_type == "m.room.encrypted":
        return "encrypted-unavailable", "unavailable"
    if event.get("redacted_because") is not None:
        return "redaction", "redacted"
    if event_type.startswith("m.call."):
        return "call", "available"
    if event_type == "m.room.message":
        msgtype = content.get("msgtype")
        if msgtype in {"m.file", "m.image", "m.video", "m.audio"}:
            return "attachment", "available"
        relation = content.get("m.relates_to")
        if isinstance(relation, dict) and relation.get("rel_type") == "m.replace":
            return "edit", "available"
        return "message", "available"
    return "state", "available"


def relation_ids(content: dict[str, Any]) -> list[str]:
    relation = content.get("m.relates_to")
    if not isinstance(relation, dict):
        return []
    values: list[str] = []
    direct = relation.get("event_id")
    if isinstance(direct, str) and direct:
        values.append(direct)
    reply = relation.get("m.in_reply_to")
    if isinstance(reply, dict):
        reply_id = reply.get("event_id")
        if isinstance(reply_id, str) and reply_id:
            values.append(reply_id)
    return list(dict.fromkeys(values))


def safe_basename(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    name = PurePosixPath(value.replace("\\", "/")).name
    return name if name not in {"", ".", ".."} else None


def revision_id(source_id: str, archive_sha256: str, event_keys: list[str]) -> str:
    event_digest = hashlib.sha256("\n".join(event_keys).encode("utf-8")).hexdigest()
    return opaque_key("rev", f"{source_id}\0{archive_sha256}\0{PARSER_VERSION}\0{event_digest}")


def build_records(path: str, source_id: str, archive_sha256: str | None = None) -> dict[str, Any]:
    if not source_id or any(char.isspace() for char in source_id):
        raise ArchiveError("source_id must be a nonempty stable identifier")
    document, members, root, member_count = load_element_export(path)
    actual_digest = sha256_path(path)
    if archive_sha256 is not None and archive_sha256 != actual_digest:
        raise ArchiveError("archive digest does not match the supplied identity")
    raw_events = document["messages"]
    seen_identities: set[tuple[str, str]] = set()
    draft: list[dict[str, Any]] = []
    locator_events: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_events):
        if not isinstance(raw, dict):
            raise ArchiveError(f"unsupported event shape at index {index}")
        event_id, room_id, event_type = raw.get("event_id"), raw.get("room_id"), raw.get("type")
        content = raw.get("content")
        if not all(isinstance(value, str) and value for value in (event_id, room_id, event_type)) or not isinstance(content, dict):
            raise ArchiveError(f"unsupported event shape at index {index}")
        identity = (room_id, event_id)
        if identity in seen_identities:
            raise ArchiveError("export contains duplicate room/event identities")
        seen_identities.add(identity)
        event_key = opaque_key("ev", f"{source_id}\0{room_id}\0{event_id}")
        locator_ref = opaque_key("pl", f"{source_id}\0{room_id}\0{event_id}")
        kind, availability = event_kind(raw, content)
        draft.append({
            "event_key": event_key,
            "occurred_at": timestamp(raw.get("origin_server_ts")),
            "kind": kind,
            "availability": availability,
            "protected_locator_ref": locator_ref,
            "_room_id": room_id,
            "_event_id": event_id,
            "_relations": relation_ids(content),
            "_content": content,
            "_index": index,
        })
        locator_events[locator_ref] = {
            "room_id": room_id,
            "event_id": event_id,
            "json_pointer": f"/messages/{index}",
        }
    calculated_revision = revision_id(source_id, actual_digest, [entry["event_key"] for entry in draft])
    by_identity = {(entry["_room_id"], entry["_event_id"]): entry["event_key"] for entry in draft}
    events: list[dict[str, Any]] = []
    for entry in draft:
        relations = [by_identity.get((entry["_room_id"], raw_id), opaque_key("ev", f"{source_id}\0{entry['_room_id']}\0{raw_id}")) for raw_id in entry["_relations"]]
        events.append({
            "event_key": entry["event_key"],
            "revision_id": calculated_revision,
            "occurred_at": entry["occurred_at"],
            "kind": entry["kind"],
            "availability": entry["availability"],
            "relations": relations,
            "protected_locator_ref": entry["protected_locator_ref"],
        })

    attachment_members = [info for info in members if PurePosixPath(info.filename).name != "export.json"]
    member_by_name: dict[str, list[zipfile.ZipInfo]] = {}
    for info in attachment_members:
        member_by_name.setdefault(PurePosixPath(info.filename).name, []).append(info)
    attachments: list[dict[str, Any]] = []
    locator_members: dict[str, dict[str, Any]] = {}
    for entry in draft:
        if entry["kind"] != "attachment":
            continue
        name = safe_basename(entry["_content"].get("body"))
        candidates = member_by_name.get(name, []) if name else []
        declared = entry["_content"].get("info", {}).get("size") if isinstance(entry["_content"].get("info"), dict) else None
        if len(candidates) == 1:
            member = candidates[0]
            status = "candidate"
        else:
            size_candidates = [item for item in attachment_members if isinstance(declared, int) and item.file_size == declared]
            if len(size_candidates) == 1:
                # A size-only association is useful for review but never
                # establishes that an encrypted Matrix attachment is verified.
                member = size_candidates[0]
                status = "candidate"
            else:
                member = None
                status = "disputed" if isinstance(declared, int) else "missing"
        if member is not None:
            member_ref = opaque_key("pm", f"{source_id}\0{member.filename}")
            locator_members[member_ref] = {"archive_member": member.filename, "size": member.file_size}
        else:
            member_ref = None
        attachments.append({
            "attachment_key": opaque_key("at", entry["event_key"]),
            "event_key": entry["event_key"],
            "mapping_status": status,
            "review_state": "pending" if status == "candidate" else "disputed",
            **({"protected_member_ref": member_ref} if member_ref else {}),
        })

    event_dispositions = [
        {"unit_key": event["event_key"], "unit_type": "event", "disposition": "unavailable" if event["availability"] == "unavailable" else "pending"}
        for event in events
    ]
    attachment_dispositions = [
        {"unit_key": attachment["attachment_key"], "unit_type": "attachment", "disposition": "disputed" if attachment["mapping_status"] != "candidate" else "pending"}
        for attachment in attachments
    ]
    worklist = event_dispositions + attachment_dispositions
    counts: dict[str, int] = {}
    for unit in worklist:
        counts[unit["disposition"]] = counts.get(unit["disposition"], 0) + 1
    revision = {
        "schema_version": 1,
        "source_id": source_id,
        "archive_sha256": actual_digest,
        "revision_id": calculated_revision,
        "parser_version": PARSER_VERSION,
        "events": events,
    }
    protected_map = {
        "format": 1,
        "source_id": source_id,
        "revision_id": calculated_revision,
        "archive_sha256": actual_digest,
        "archive_path": os.path.abspath(path),
        "events": locator_events,
        "members": locator_members,
    }
    return {
        "revision": revision,
        "attachments": {"schema_version": 1, "source_id": source_id, "revision_id": calculated_revision, "attachments": attachments},
        "worklist": {"schema_version": 1, "source_id": source_id, "revision_id": calculated_revision, "units": worklist, "counts": counts},
        "protected_map": protected_map,
        "summary": {
            "ok": True,
            "source_shape": "element-export",
            "events": len(events),
            "members": member_count,
            "attachments": len(attachments),
            "unavailable_events": sum(event["availability"] == "unavailable" for event in events),
            "attachment_mapping": {status: sum(item["mapping_status"] == status for item in attachments) for status in ("candidate", "verified", "disputed", "missing")},
            "revision_id": calculated_revision,
        },
    }


def canonical_json(record: Any) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


def write_immutable(path: str, payload: bytes, mode: int = 0o600) -> str:
    target = os.path.abspath(path)
    parent = os.path.dirname(target)
    os.makedirs(parent, mode=0o700, exist_ok=True)
    try:
        with open(target, "xb") as handle:
            os.chmod(target, mode)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return "created"
    except FileExistsError:
        with open(target, "rb") as handle:
            if handle.read() == payload:
                return "unchanged"
        raise ArchiveError("immutable output already exists with different content")
