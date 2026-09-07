#!/usr/bin/env python3
"""Build a safe, non-applying pilot batch from a protected Matrix locator map."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any


class PilotError(RuntimeError):
    pass


PILOTS = (
    ("feather-tor", ("feather-install", "feather-proxy", "tor-daemons"), "Incidents/Feather Tor Historical Reports.md", "Historical evidence records configuration attempts and conflicting reported outcomes. This candidate makes no claim about current working settings."),
    ("smartcard-recovery", ("smartcard",), "Incidents/Smartcard Recovery History.md", "Historical evidence records failed recovery attempts and a reported recovery. It is not a verified reusable procedure."),
    ("docker-matrix-membership", ("docker-warning",), "Incidents/Docker Warning and Matrix Membership.md", "Screenshot-only Docker-warning evidence and Matrix membership events remain separate. Their causal relationship and outcomes are unresolved."),
)


def load(path: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotError(f"cannot read required JSON: {Path(path).name}") from exc
    if not isinstance(data, dict):
        raise PilotError(f"required JSON is not an object: {Path(path).name}")
    return data


def canonical_digest(record: dict[str, Any]) -> str:
    material = {key: value for key, value in record.items() if key not in {"digest", "accepted_digest", "apply_authorized"}}
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def safe_markdown(title: str, body: str, source_path: str, source_id: str, revision_id: str, evidence_keys: list[str]) -> str:
    anchors = ", ".join(evidence_keys)
    return "\n".join((
        "---",
        f"title: {title}",
        "type: incident",
        "evidence-status: participant-reported",
        "verification-status: unverified",
        "sources:",
        f"  - {source_path}",
        "---",
        "",
        f"# {title}",
        "",
        body,
        "",
        "This is a reviewable pilot candidate. It preserves uncertainty and does not authorize a current procedure.",
        "",
        f"Safe evidence anchors: {anchors}",
        "",
        f"<!-- source-id: {source_id}; revision-id: {revision_id} -->",
        "",
    ))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--worklist", required=True)
    parser.add_argument("--attachments", required=True)
    parser.add_argument("--protected-map", required=True)
    parser.add_argument("--evidence-map", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        revision = load(args.revision)
        worklist = load(args.worklist)
        attachments = load(args.attachments)
        protected = load(args.protected_map)
        evidence = load(args.evidence_map)
        source_id, revision_id = revision.get("source_id"), revision.get("revision_id")
        if not isinstance(source_id, str) or not isinstance(revision_id, str):
            raise PilotError("revision identity is invalid")
        locator_to_key = {event.get("protected_locator_ref"): event.get("event_key") for event in revision.get("events", []) if isinstance(event, dict)}
        raw_to_key = {item.get("event_id"): locator_to_key.get(locator) for locator, item in protected.get("events", {}).items() if isinstance(item, dict)}
        arc_evidence = {arc.get("arc_id"): arc.get("evidence", []) for arc in evidence.get("arcs", []) if isinstance(arc, dict)}
        source_path = f"raw/extracts/{source_id}/{revision_id}/p5-pilot.md"
        pilot_claims: list[dict[str, Any]] = []
        pilot_sections: list[str] = []
        changes: list[dict[str, Any]] = []
        for pilot_id, arc_ids, destination, summary in PILOTS:
            keys = []
            for arc_id in arc_ids:
                if arc_id not in arc_evidence:
                    raise PilotError("required pilot arc is absent from the evidence map")
                for item in arc_evidence[arc_id]:
                    if not isinstance(item, dict) or not isinstance(item.get("event_id"), str):
                        raise PilotError("evidence map contains malformed locator")
                    event_key = raw_to_key.get(item["event_id"])
                    if not isinstance(event_key, str):
                        raise PilotError("evidence locator does not resolve to the staged revision")
                    keys.append(event_key)
            keys = sorted(set(keys))
            if not keys:
                raise PilotError("pilot arc resolved to no source units")
            pilot_claims.append({"claim_id": f"cl_{pilot_id}", "evidence_keys": keys, "destinations": [destination], "status": "proposed", "resolution": "unresolved"})
            pilot_sections.extend((f"## {pilot_id}", "", summary, "", f"Safe evidence anchors: {', '.join(keys)}", ""))
            changes.append({"path": destination, "before_sha256": None, "content": safe_markdown(Path(destination).stem, summary, source_path, source_id, revision_id, keys)})
        source_card = "\n".join((
            "---", "title: Matrix Conversation Source", "type: source", f"source-id: {source_id}",
            f"revision-id: {revision_id}", "inventory-status: complete", "extraction-status: pilot-pending-review", "---", "",
            "# Matrix Conversation Source", "", "This source card names an opaque, protected Matrix archive revision.",
            "It records inventory and review limits without exposing participant or room identity.", "",
            f"Inventory: {len(revision.get('events', []))} events; {len(attachments.get('attachments', []))} attachments; 5 unavailable encrypted events; 5 disputed attachment mappings.", "",
        ))
        changes.insert(0, {"path": "Sources/Matrix Conversation Source.md", "before_sha256": None, "content": source_card})
        extract = "\n".join((
            "---", f"source-id: {source_id}", f"revision-id: {revision_id}", "extract-kind: p5-pilot", "review-status: pending-owner-acceptance", "---", "",
            "# P5 Matrix pilot extract", "", "This safe extract is a candidate review record. It contains no raw messages, identities, attachment bytes, credentials, or original locators.", "", *pilot_sections,
        ))
        changes.insert(1, {"path": source_path, "before_sha256": None, "content": extract})
        units = worklist.get("units", [])
        if not isinstance(units, list) or not units:
            raise PilotError("worklist is invalid")
        batch = {
            "schema_version": 1,
            "batch_id": f"p5-{revision_id}",
            "source_id": source_id,
            "revision_id": revision_id,
            "coverage": {"total_units": len(units), "accounted_units": len(units)},
            "coverage_dispositions": worklist.get("counts", {}),
            "claims": pilot_claims,
            "attachments": [{"attachment_key": item.get("attachment_key"), "review_state": item.get("review_state")} for item in attachments.get("attachments", [])],
            "index_status": "unchanged",
            "changes": changes,
        }
        batch["digest"] = canonical_digest(batch)
        destination = Path(args.output)
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        encoded = json.dumps(batch, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
        try:
            with open(destination, "xb") as handle:
                os.chmod(destination, 0o600)
                handle.write(encoded)
        except FileExistsError:
            if destination.read_bytes() != encoded:
                raise PilotError("exact pilot batch path already holds different content")
        print(json.dumps({"ok": True, "batch_id": batch["batch_id"], "digest": batch["digest"], "claims": len(pilot_claims), "changes": len(changes), "coverage": batch["coverage"], "dispositions": worklist.get("counts", {})}, sort_keys=True))
    except PilotError as exc:
        print(f"prepare-chat-pilot: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
