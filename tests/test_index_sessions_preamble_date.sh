#!/usr/bin/env bash
# test_index_sessions_preamble_date.sh — the session start date must survive an
# untimestamped preamble.
#
# Regression: the Claude Code lane read exactly one line to find the start date.
# Recent builds emit header events with no `timestamp` field — `last-prompt`,
# `mode`, `permission-mode`, `bridge-session` — before the first real event, so
# line 1 alone yielded nothing and every such session silently fell back to the
# file mtime. mtime is the LAST write, so long sessions were dated days late:
# one 30-day worklist had 224 of 606 rows on the mtime fallback, and 64 of them
# were already imported under their true date. Re-importing would have written
# 64 duplicate pages, each dated wrong.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT" || exit 1
fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

IDX="plugins/obsidian-wiki/scripts/index-sessions.py"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP"

proj="$TMP/.claude/projects/-home-user-dev-demo"
mkdir -p "$proj"
sess="$proj/fbe618c2-e8d5-4d12-9d44-e280d3788790.jsonl"

# Four untimestamped preamble events, then the first real (timestamped) one.
{
    printf '{"type":"last-prompt","sessionId":"fbe618c2","leafUuid":"x"}\n'
    printf '{"type":"mode","sessionId":"fbe618c2","mode":"default"}\n'
    printf '{"type":"permission-mode","sessionId":"fbe618c2","permissionMode":"plan"}\n'
    printf '{"type":"bridge-session","sessionId":"fbe618c2","lastSequenceNum":0}\n'
    printf '{"type":"user","timestamp":"2026-08-05T09:12:00Z","message":{"role":"user","content":"start"}}\n'
    printf '{"type":"assistant","timestamp":"2026-08-08T18:40:00Z","message":{"role":"assistant","content":"later"}}\n'
} > "$sess"

# The session ran for days: mtime is 2026-08-08, three days past its true start.
touch -d '2026-08-08T18:40:00Z' "$sess"

out="$TMP/idx.json"
python3 "$IDX" --days 3650 --tool claude-code --out "$out" >/dev/null 2>&1 \
    || fail "indexer exited non-zero"

python3 - "$out" <<'PY' || exit 1
import json, sys
s = json.load(open(sys.argv[1]))["tools"]["claude-code"]["sessions"]
assert len(s) == 1, f"expected 1 session, got {len(s)}"
r = s[0]
assert r["date_source"] == "first-event", (
    f"date_source is {r['date_source']!r} — the untimestamped preamble sent it "
    f"to the mtime fallback")
assert r["date"] == "2026-08-05", (
    f"date is {r['date']!r}, expected 2026-08-05 (first timestamped event); "
    f"2026-08-08 means it used the file mtime")
print("  ok: first timestamped event found past the preamble")
print("  ok: date is the session start, not the last write")
PY

ok "untimestamped preamble does not force the mtime fallback"
echo "ALL OK"
