#!/usr/bin/env bash
# test_index_sessions_shape.sh — the session index must contain sessions only.
#
# Regression: the first version walked ~/.claude/projects recursively and counted
# <project>/<uuid>/subagents/agent-*.jsonl as sessions. A 30-day window held 1071
# subagent transcripts against 464 real sessions, so an import driven off that
# index would have been mostly dispatched-agent chatter. The Codex lane already
# filtered its own `thread_source: subagent`; this asserts the Claude Code side.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT" || exit 1
fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

IDX="plugins/obsidian-wiki/scripts/index-sessions.py"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP"

proj="$TMP/.claude/projects/-home-user-dev-demo"
mkdir -p "$proj/9fc86fd8-3068-46c7-ac1f-b87a6b1a0f6f/subagents"
# a real session: UUID-named, directly under the project dir
printf '{"type":"user","timestamp":"2026-08-14T10:00:00Z","message":{"role":"user","content":"hi"}}\n' \
    > "$proj/3c6ed25c-7eed-4926-b750-3b31ca8b1f92.jsonl"
# a subagent transcript, one level deeper
printf '{"type":"user","message":{"role":"user","content":"dispatched"}}\n' \
    > "$proj/9fc86fd8-3068-46c7-ac1f-b87a6b1a0f6f/subagents/agent-a1f91361002d44cdf.jsonl"
# a non-UUID file directly in the project dir (not a session either)
printf '{}\n' > "$proj/notes.jsonl"

out="$TMP/idx.json"
python3 "$IDX" --days 3650 --tool claude-code --out "$out" >/dev/null 2>&1 \
    || fail "indexer exited non-zero"

python3 - "$out" <<'PY' || exit 1
import json, sys
d = json.load(open(sys.argv[1]))
s = d["tools"]["claude-code"]["sessions"]
paths = [x["path"] for x in s]
assert len(s) == 1, f"expected exactly 1 session, got {len(s)}: {paths}"
assert paths[0].endswith("3c6ed25c-7eed-4926-b750-3b31ca8b1f92.jsonl"), paths
assert not any("/subagents/" in p for p in paths), "subagent transcript indexed"
assert not any(p.endswith("notes.jsonl") for p in paths), "non-UUID file indexed"
assert s[0]["date"] == "2026-08-14", f"date should come from the first event: {s[0]}"
assert s[0]["date_source"] == "first-event", s[0]
print("  ok: only the UUID-named session at depth 0 is indexed")
print("  ok: date taken from the first event, not mtime")
PY

ok "subagent transcripts and non-session files excluded"
echo "ALL OK"
