#!/usr/bin/env python3
"""Commit one already-sanitized Matrix revision under exclusive maintenance.

This command never reads the original archive. It copies an already-validated
safe staging set into the vault's excluded raw tree and keeps the identity map
in a protected companion root outside the vault.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

from vault_write_protocol import ProtocolError, finish, require_write_access, start, vault_root


class CommitError(RuntimeError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CommitError(f"cannot read staged JSON: {path.name}") from exc
    if not isinstance(record, dict):
        raise CommitError(f"staged JSON is not an object: {path.name}")
    return record


def atomic_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".chat-revision-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def copy_immutable(source: Path, target: Path, mode: int) -> str:
    if not source.is_file() or source.is_symlink():
        raise CommitError(f"staged input is not a regular file: {source.name}")
    payload = source.read_bytes()
    if target.exists():
        if target.is_file() and not target.is_symlink() and target.read_bytes() == payload:
            return "unchanged"
        raise CommitError(f"immutable target already exists with different content: {target.name}")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(target, "xb") as handle:
        os.chmod(target, mode)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return "created"


def revision_manifest(revision: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
    required = ("schema_version", "source_id", "archive_sha256", "revision_id", "events")
    if any(key not in revision for key in required) or revision.get("schema_version") != 1:
        raise CommitError("staged revision is not contract version 1")
    events = revision["events"]
    if not isinstance(events, list) or not events:
        raise CommitError("staged revision has no events")
    source_id = revision["source_id"]
    if not isinstance(source_id, str) or not source_id:
        raise CommitError("staged revision has invalid source_id")
    prior = [] if existing is None else existing.get("revisions", [])
    if not isinstance(prior, list) or any(not isinstance(item, str) for item in prior):
        raise CommitError("existing registry has invalid revisions")
    revision_id = revision["revision_id"]
    return {
        "schema_version": 1,
        "source_id": source_id,
        "archive_sha256": revision["archive_sha256"],
        "source_language": "ru",
        "event_period_start": min(event["occurred_at"] for event in events),
        "event_period_end": max(event["occurred_at"] for event in events),
        "inventory_status": "complete",
        "revisions": list(dict.fromkeys([*prior, revision_id])),
        "unrecovered_event_count": sum(event.get("availability") == "unavailable" for event in events),
        "structural_rehearsal_replaced": bool(existing),
    }


def commit(args: argparse.Namespace) -> dict[str, Any]:
    vault = vault_root(args.vault)
    staging = Path(args.staging).resolve()
    protected_root = Path(args.protected_root).resolve()
    if protected_root.is_relative_to(vault):
        raise CommitError("protected companion root must be outside the vault")
    sources = {
        "revision.json": staging / "revision.json",
        "events.redacted.jsonl": staging / "events.redacted.jsonl",
        "media-manifest.json": staging / "media-manifest.json",
        "worklist.json": staging / "worklist.json",
        "protected-map.json": staging / "protected-map.json",
    }
    revision = load_json(sources["revision.json"])
    attachments = load_json(sources["media-manifest.json"])
    worklist = load_json(sources["worklist.json"])
    protected = load_json(sources["protected-map.json"])
    source_id, revision_id = revision.get("source_id"), revision.get("revision_id")
    if not isinstance(source_id, str) or not isinstance(revision_id, str):
        raise CommitError("staged revision has unsafe identity")
    if any(record.get("source_id") != source_id or record.get("revision_id") != revision_id for record in (attachments, worklist, protected)):
        raise CommitError("staged artifact identities do not agree")
    if protected.get("archive_sha256") != revision.get("archive_sha256"):
        raise CommitError("protected map does not agree with revision digest")
    revision_dir = vault / "raw" / "conversations" / source_id / "revisions" / revision_id
    registry_path = vault / "raw" / "conversations" / source_id / "manifest.json"
    protected_target = protected_root / source_id / "revisions" / revision_id / "locator-map.json"
    journal_path = vault / ".obsidian-wiki" / "chat-revision-journals" / f"{revision_id}.json"
    if journal_path.exists():
        existing_journal = load_json(journal_path)
        if existing_journal.get("revision_sha256") != digest(sources["revision.json"]):
            raise CommitError("existing revision journal does not match staged revision")
        if existing_journal.get("state") == "committed":
            return {"state": "already-committed", "revision_id": revision_id}
        raise CommitError("incomplete revision journal requires recovery before retry")
    existing = load_json(registry_path) if registry_path.exists() else None
    registry = revision_manifest(revision, existing)
    journal = {
        "format": 1,
        "state": "planned",
        "source_id": source_id,
        "revision_id": revision_id,
        "revision_sha256": digest(sources["revision.json"]),
        "registry_before_sha256": digest(registry_path) if registry_path.exists() else None,
        "files": [],
    }
    atomic_json(journal_path, journal)
    targets = (
        ("revision", sources["revision.json"], revision_dir / "revision.json", 0o644),
        ("events", sources["events.redacted.jsonl"], revision_dir / "events.redacted.jsonl", 0o644),
        ("media", sources["media-manifest.json"], revision_dir / "media-manifest.json", 0o644),
        ("worklist", sources["worklist.json"], revision_dir / "worklist.json", 0o644),
        ("protected_map", sources["protected-map.json"], protected_target, 0o600),
    )
    try:
        for name, source, target, mode in targets:
            require_write_access(vault, args.maintenance_token)
            result = copy_immutable(source, target, mode)
            journal["files"].append({"name": name, "sha256": digest(source), "result": result})
            journal["state"] = "copying"
            atomic_json(journal_path, journal)
        require_write_access(vault, args.maintenance_token)
        atomic_json(registry_path, registry)
        journal["state"] = "committed"
        journal["registry_after_sha256"] = digest(registry_path)
        atomic_json(journal_path, journal)
    except Exception:
        journal["state"] = "incomplete"
        atomic_json(journal_path, journal)
        raise
    return {"state": "committed", "revision_id": revision_id, "journal": str(journal_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True)
    parser.add_argument("--staging", required=True)
    parser.add_argument("--protected-root", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--lease-seconds", type=int, default=900)
    args = parser.parse_args()
    try:
        vault = vault_root(args.vault)
        started = start(vault, args.owner, "commit Matrix sanitized revision", args.lease_seconds)
        try:
            args.maintenance_token = started["token"]
            result = commit(args)
        finally:
            finish(vault, started["token"])
        print(json.dumps(result, sort_keys=True))
    except (CommitError, ProtocolError) as exc:
        print(f"commit-chat-revision: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
