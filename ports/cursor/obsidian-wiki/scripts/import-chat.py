#!/usr/bin/env python3
"""Safely inventory the supported Element Matrix ZIP shape without extracting it."""
import argparse, json, os, sys, zipfile

MAX_MEMBERS = 10000

def fail(errors, as_json):
    out = {"ok": False, "errors": errors}
    print(json.dumps(out, sort_keys=True) if as_json else "ERROR: " + "; ".join(errors))
    return 2

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archive")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        with zipfile.ZipFile(args.archive) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_MEMBERS: return fail(["archive has too many members"], args.json)
            for info in infos:
                name = info.filename
                if name.startswith("/") or ".." in name.split("/") or "\\" in name:
                    return fail([f"unsafe member path: {name}"], args.json)
                if info.is_dir() or not name.endswith("export.json"): continue
                export = info
                break
            else: return fail(["missing export.json"], args.json)
            data = json.loads(archive.read(export))
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        return fail([f"unsupported archive: {exc}"], args.json)
    messages = data.get("messages")
    if not isinstance(messages, list): return fail(["unsupported Element export shape"], args.json)
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or not isinstance(message.get("event_id"), str) or not isinstance(message.get("type"), str):
            return fail([f"unsupported event shape at messages[{index}]"], args.json)
    out = {"ok": True, "source_shape": "element-export", "events": len(messages), "members": len(infos)}
    print(json.dumps(out, sort_keys=True) if args.json else f"events={len(messages)}")
    return 0

if __name__ == "__main__": sys.exit(main())
