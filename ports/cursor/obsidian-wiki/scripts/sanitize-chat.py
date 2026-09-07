#!/usr/bin/env python3
"""Render event-faithful, identity-safe JSONL records."""
import hashlib, json, sys
for line in open(sys.argv[1], encoding="utf-8"):
    raw=json.loads(line); identity=str(raw.get("event_id", ""))
    print(json.dumps({"event_key":"ev_"+hashlib.sha256(identity.encode()).hexdigest()[:16], "kind":"message", "availability":"available"}, sort_keys=True))
