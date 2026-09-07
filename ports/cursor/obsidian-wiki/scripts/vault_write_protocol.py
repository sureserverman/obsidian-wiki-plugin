#!/usr/bin/env python3
"""Explicit maintenance-mode writer gate for a shared Obsidian vault.

This is deliberately *not* presented as a distributed lock.  Some supported
vault mounts do not provide a lock primitive whose cross-host semantics have
been demonstrated.  During an owner-confirmed exclusive maintenance window,
this module records the one permitted writer and makes participating scripts
refuse every other write.  A stale window blocks writers until an operator
explicitly recovers it; it is never silently stolen.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import tempfile
from typing import Any

CONTROL_DIR = ".obsidian-wiki"
MANIFEST_NAME = "maintenance.json"
FORMAT_VERSION = 1


class ProtocolError(RuntimeError):
    """The maintenance contract disallows the requested operation."""


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def as_timestamp(value: dt.datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: object) -> dt.datetime:
    if not isinstance(value, str):
        raise ProtocolError("maintenance manifest has no valid timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProtocolError("maintenance manifest has an invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise ProtocolError("maintenance manifest timestamp has no timezone")
    return parsed.astimezone(dt.timezone.utc)


def vault_root(value: str) -> Path:
    root = Path(value).resolve()
    if not root.is_dir():
        raise ProtocolError(f"vault does not exist: {root}")
    return root


def manifest_path(root: Path) -> Path:
    return root / CONTROL_DIR / MANIFEST_NAME


def read_manifest(root: Path) -> dict[str, Any] | None:
    path = manifest_path(root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("maintenance manifest cannot be read safely") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT_VERSION:
        raise ProtocolError("maintenance manifest has an unsupported format")
    return data


def is_expired(manifest: dict[str, Any], at: dt.datetime | None = None) -> bool:
    return parse_timestamp(manifest.get("expires_at")) <= (at or now_utc())


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    # Prefix capabilities so a token can always be passed as the value of a
    # conventional ``--token VALUE`` CLI option; urlsafe randomness may begin
    # with ``-`` and otherwise looks like another option to argparse.
    return "m_" + secrets.token_urlsafe(32)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".maintenance-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def make_manifest(owner: str, purpose: str, lease_seconds: int, token: str) -> dict[str, Any]:
    started = now_utc()
    return {
        "format": FORMAT_VERSION,
        "mode": "exclusive-maintenance",
        "owner": owner,
        "purpose": purpose,
        "host": socket.gethostname(),
        "started_at": as_timestamp(started),
        "expires_at": as_timestamp(started + dt.timedelta(seconds=lease_seconds)),
        "token_sha256": token_digest(token),
    }


def start(root: Path, owner: str, purpose: str, lease_seconds: int) -> dict[str, Any]:
    existing = read_manifest(root)
    if existing is not None:
        if is_expired(existing):
            raise ProtocolError("maintenance window is stale; run recover with explicit acknowledgement")
        raise ProtocolError("an exclusive maintenance window is already active")
    token = new_token()
    manifest = make_manifest(owner, purpose, lease_seconds, token)
    # Mutual exclusion comes from the owner-confirmed maintenance window, not
    # from os.replace.  Do not use this operation concurrently on unproven
    # network filesystems.
    write_json(manifest_path(root), manifest)
    return {"token": token, "manifest": manifest}


def require_write_access(root: Path, token: str | None = None) -> None:
    manifest = read_manifest(root)
    if manifest is None:
        return
    if is_expired(manifest):
        raise ProtocolError("maintenance window expired; explicit recovery is required before writes")
    candidate = token or os.environ.get("OBSIDIAN_WIKI_MAINTENANCE_TOKEN", "")
    expected = manifest.get("token_sha256")
    if not isinstance(expected, str) or not candidate or not secrets.compare_digest(expected, token_digest(candidate)):
        raise ProtocolError("write refused: another owner holds the exclusive maintenance window")


def finish(root: Path, token: str | None = None) -> None:
    manifest = read_manifest(root)
    if manifest is None:
        raise ProtocolError("no maintenance window is active")
    expected = manifest.get("token_sha256")
    candidate = token or os.environ.get("OBSIDIAN_WIKI_MAINTENANCE_TOKEN", "")
    if not isinstance(expected, str) or not candidate or not secrets.compare_digest(expected, token_digest(candidate)):
        raise ProtocolError("only the active maintenance owner may finish the window")
    manifest_path(root).unlink()


def recover(root: Path, owner: str, purpose: str, lease_seconds: int, acknowledge_stale: bool) -> dict[str, Any]:
    existing = read_manifest(root)
    if existing is None:
        raise ProtocolError("no stale maintenance window exists")
    if not is_expired(existing):
        raise ProtocolError("maintenance window is still active")
    if not acknowledge_stale:
        raise ProtocolError("recovery requires --acknowledge-stale after checking the prior owner")
    history = root / CONTROL_DIR / "maintenance-history"
    previous = history / f"{parse_timestamp(existing['started_at']).strftime('%Y%m%dT%H%M%SZ')}.json"
    if previous.exists():
        raise ProtocolError("stale maintenance history already exists; inspect it before recovery")
    write_json(previous, existing)
    token = new_token()
    manifest = make_manifest(owner, purpose, lease_seconds, token)
    write_json(manifest_path(root), manifest)
    return {"token": token, "manifest": manifest}


def public_state(root: Path) -> dict[str, Any]:
    manifest = read_manifest(root)
    if manifest is None:
        return {"state": "open"}
    return {
        "state": "expired" if is_expired(manifest) else "active",
        "owner": manifest.get("owner"),
        "purpose": manifest.get("purpose"),
        "host": manifest.get("host"),
        "started_at": manifest.get("started_at"),
        "expires_at": manifest.get("expires_at"),
    }


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--vault", required=True)
    sub = cli.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    check = sub.add_parser("check")
    check.add_argument("--token")
    for name in ("start", "recover"):
        command = sub.add_parser(name)
        command.add_argument("--owner", required=True)
        command.add_argument("--purpose", required=True)
        command.add_argument("--lease-seconds", type=int, required=True)
    sub.choices["recover"].add_argument("--acknowledge-stale", action="store_true")
    for name in ("finish",):
        command = sub.add_parser(name)
        command.add_argument("--token")
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = vault_root(args.vault)
        if getattr(args, "lease_seconds", 1) < 1:
            raise ProtocolError("lease must be at least one second")
        if args.command == "status":
            print(json.dumps(public_state(root), sort_keys=True))
        elif args.command == "check":
            require_write_access(root, args.token)
            print(json.dumps(public_state(root), sort_keys=True))
        elif args.command == "start":
            print(json.dumps(start(root, args.owner, args.purpose, args.lease_seconds), sort_keys=True))
        elif args.command == "finish":
            finish(root, args.token)
            print(json.dumps({"state": "open"}, sort_keys=True))
        else:
            print(json.dumps(recover(root, args.owner, args.purpose, args.lease_seconds, args.acknowledge_stale), sort_keys=True))
    except ProtocolError as exc:
        print(f"vault-write-protocol: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
