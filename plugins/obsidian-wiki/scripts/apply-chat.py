#!/usr/bin/env python3
"""Apply or recover one accepted Matrix chat batch with a durable file journal."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

from vault_write_protocol import ProtocolError, require_write_access

SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ApplyError(RuntimeError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_digest(batch: dict[str, Any]) -> str:
    material = {key: value for key, value in batch.items() if key not in {"digest", "accepted_digest", "apply_authorized"}}
    return digest(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApplyError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ApplyError("JSON record must be an object")
    return value


def validate_batch_file(path: Path) -> None:
    validator = Path(__file__).with_name("validate-chat.py")
    result = subprocess.run([sys.executable, str(validator), "--batch", str(path), "--json"],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise ApplyError("batch validation failed before any write")


def sha_file(path: Path) -> str | None:
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise ApplyError(f"target is not a regular file: {path}")
    return digest(path.read_bytes())


def safe_relative(value: object) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ApplyError("change path must be a nonempty slash-separated relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ApplyError(f"unsafe change path: {value}")
    return path


def permitted_target(vault: Path, relative: Path, roots: list[Path]) -> Path:
    if relative in {Path("log.md"), Path("index.md")}:
        target = vault / relative
    else:
        target = vault / relative
        if not any(relative.is_relative_to(root) for root in roots):
            raise ApplyError(f"target is outside the allowed roots: {relative}")
    parent = target.parent.resolve()
    if not parent.is_relative_to(vault):
        raise ApplyError(f"target parent escapes vault: {relative}")
    if target.exists() and not target.resolve().is_relative_to(vault):
        raise ApplyError(f"target escapes vault: {relative}")
    return target


def write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ApplyError(f"target directory is unsafe: {path.parent}")
    fd, temporary = tempfile.mkstemp(prefix=".chat-stage-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def write_json(path: Path, record: dict[str, Any]) -> None:
    encoded = json.dumps(record, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    write_bytes(path, encoded)


def parse_batch(batch: dict[str, Any], vault: Path, roots: list[Path], accepted: str) -> tuple[str, list[dict[str, Any]]]:
    if batch.get("schema_version") != 1:
        raise ApplyError("unsupported batch schema_version")
    identifier = batch.get("batch_id")
    if not isinstance(identifier, str) or not identifier or "/" in identifier or ".." in identifier:
        raise ApplyError("batch_id must be a safe nonempty identifier")
    actual = canonical_digest(batch)
    if batch.get("digest") != actual or accepted != actual:
        raise ApplyError("accepted digest does not match the exact batch")
    changes = batch.get("changes")
    if not isinstance(changes, list) or not changes:
        raise ApplyError("batch must contain one or more changes")
    parsed: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for item in changes:
        if not isinstance(item, dict):
            raise ApplyError("each change must be an object")
        relative = safe_relative(item.get("path"))
        if relative in seen:
            raise ApplyError(f"batch changes a target more than once: {relative}")
        seen.add(relative)
        target = permitted_target(vault, relative, roots)
        expected = item.get("before_sha256")
        if expected is not None and (not isinstance(expected, str) or not SHA256.fullmatch(expected)):
            raise ApplyError(f"invalid before_sha256 for {relative}")
        content = item.get("content")
        if not isinstance(content, str):
            raise ApplyError(f"change content must be text: {relative}")
        parsed.append({"path": relative.as_posix(), "target": target, "expected": expected, "content": content.encode("utf-8")})
    return identifier, parsed


def journal_path(vault: Path, identifier: str) -> Path:
    return vault / ".obsidian-wiki" / "chat-journals" / f"{identifier}.json"


def checked_journal(path: Path) -> dict[str, Any] | None:
    return load(path) if path.exists() else None


def apply(batch_path: Path, vault: Path, roots: list[Path], accepted: str) -> dict[str, Any]:
    validate_batch_file(batch_path)
    batch = load(batch_path)
    identifier, changes = parse_batch(batch, vault, roots, accepted)
    journal_file = journal_path(vault, identifier)
    try:
        require_write_access(vault)
    except ProtocolError as exc:
        raise ApplyError(str(exc)) from exc
    old_journal = checked_journal(journal_file)
    if old_journal is not None:
        if old_journal.get("batch_digest") != accepted:
            raise ApplyError("journal batch digest differs; explicit recovery is required")
        if old_journal.get("state") == "committed":
            expected_posts = {entry["path"]: entry["after_sha256"] for entry in old_journal["changes"]}
            if all(sha_file(vault / path) == value for path, value in expected_posts.items()):
                return {"state": "already-committed", "batch_id": identifier}
            raise ApplyError("committed batch no longer matches its postimages; preserve the edit and resolve conflict")
        raise ApplyError("an incomplete batch journal exists; recover it before retrying")
    journal_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    records = []
    for change in changes:
        current = sha_file(change["target"])
        if current != change["expected"]:
            raise ApplyError(f"base hash conflict: {change['path']}")
        before = change["target"].read_bytes() if current is not None else None
        records.append({
            "path": change["path"],
            "before_sha256": current,
            "before_base64": base64.b64encode(before).decode("ascii") if before is not None else None,
            "after_sha256": digest(change["content"]),
            "applied": False,
        })
    journal = {"format": 1, "batch_id": identifier, "batch_digest": accepted, "state": "planned", "changes": records}
    write_json(journal_file, journal)
    test_interrupt_after = os.environ.get("OBSIDIAN_WIKI_TEST_INTERRUPT_AFTER")
    if test_interrupt_after is not None:
        try:
            interrupt_after = int(test_interrupt_after)
        except ValueError as exc:
            raise ApplyError("OBSIDIAN_WIKI_TEST_INTERRUPT_AFTER must be an integer") from exc
    else:
        interrupt_after = 0
    try:
        for sequence, (change, record) in enumerate(zip(changes, records), start=1):
            try:
                require_write_access(vault)
            except ProtocolError as exc:
                raise ApplyError(str(exc)) from exc
            if sha_file(change["target"]) != record["before_sha256"]:
                raise ApplyError(f"base hash changed during apply: {change['path']}")
            write_bytes(change["target"], change["content"])
            record["applied"] = True
            journal["state"] = "applying"
            write_json(journal_file, journal)
            if interrupt_after and sequence >= interrupt_after:
                raise ApplyError("test interruption after durable journal transition")
        journal["state"] = "committed"
        write_json(journal_file, journal)
    except Exception:
        journal["state"] = "incomplete"
        write_json(journal_file, journal)
        raise
    return {"state": "committed", "batch_id": identifier, "journal": str(journal_file)}


def recover(vault: Path, journal_file: Path) -> dict[str, Any]:
    try:
        require_write_access(vault)
    except ProtocolError as exc:
        raise ApplyError(str(exc)) from exc
    journal_root = (vault / ".obsidian-wiki" / "chat-journals").resolve()
    journal_file = journal_file.resolve()
    if not journal_file.is_relative_to(journal_root) or journal_file.suffix != ".json":
        raise ApplyError("recovery journal must be under the vault chat-journals directory")
    journal = load(journal_file)
    if journal.get("format") != 1 or not isinstance(journal.get("changes"), list):
        raise ApplyError("unsupported journal format")
    conflicts: list[str] = []
    for record in reversed(journal["changes"]):
        if not record.get("applied"):
            continue
        relative = safe_relative(record.get("path"))
        target = (vault / relative).resolve()
        if not target.is_relative_to(vault):
            raise ApplyError(f"journal target escapes vault: {relative}")
        if sha_file(target) != record.get("after_sha256"):
            conflicts.append(relative.as_posix())
            continue
        before = record.get("before_base64")
        if before is None:
            target.unlink()
        else:
            write_bytes(target, base64.b64decode(before))
        record["restored"] = True
        write_json(journal_file, journal)
    journal["state"] = "recovery-conflict" if conflicts else "recovered"
    journal["recovery_conflicts"] = conflicts
    write_json(journal_file, journal)
    return {"state": journal["state"], "conflicts": conflicts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True)
    parser.add_argument("--allow-root", action="append", default=[], help="allowed relative destination root (repeatable)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--batch")
    group.add_argument("--recover")
    parser.add_argument("--accept-digest")
    args = parser.parse_args()
    try:
        vault = Path(args.vault).resolve()
        if not vault.is_dir():
            raise ApplyError("vault does not exist")
        roots = [safe_relative(value) for value in args.allow_root]
        if args.batch:
            if not args.accept_digest:
                raise ApplyError("--accept-digest is required for an apply")
            result = apply(Path(args.batch), vault, roots, args.accept_digest)
        else:
            result = recover(vault, Path(args.recover))
        print(json.dumps(result, sort_keys=True))
    except ApplyError as exc:
        print(f"apply-chat: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
