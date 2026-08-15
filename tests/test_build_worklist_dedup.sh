#!/usr/bin/env bash
# test_build_worklist_dedup.sh — the worklist must dedup on session identity,
# never on the filename date.
#
# Regression: the hand-built worklist compared `<tool>-<date>-<short_id>` against
# the names in raw/sessions/. import-session names a file from the session's
# first-event date; the index dated many rows from the file mtime. When those
# disagreed the session read as un-imported — 64 of 606 "pending" rows were
# already in the vault under a different date, and importing would have written
# 64 duplicates. Dedup is now on source-uuid frontmatter, plus source-project for
# Cursor, whose UUIDs repeat across project contexts.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT" || exit 1
fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

BW="plugins/obsidian-wiki/scripts/build-worklist.py"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
RAW="$TMP/raw/sessions"; mkdir -p "$RAW"

# Already imported under 2026-08-11 — the index below dates the same session
# 2026-08-13 from mtime. A date-based dedup would call this fresh.
cat > "$RAW/claude-code-2026-08-11-f2eb56b0.md" <<'EOF'
---
source-tool: claude-code
source-uuid: f2eb56b0-d1e2-48ae-901f-2729036e3aa7
source-project: -home-user-dev-demo
session-turns: 12
---
EOF

# One of two Cursor sessions sharing a UUID across project contexts.
cat > "$RAW/cursor-2026-08-14-441b4e4d-emptywin.md" <<'EOF'
---
source-tool: cursor
source-uuid: 441b4e4d-119d-4dc2-93a6-7061ec579ad2
source-project: empty-window
session-turns: 44
---
EOF

cat > "$TMP/index.json" <<'EOF'
{"generated_at": "2026-08-15T00:00:00Z", "window_days": 30, "tools": {
 "claude-code": {"total": 2, "store_present": true, "sessions": [
   {"tool":"claude-code","path":"/x/f2eb56b0.jsonl","session_id":"f2eb56b0-d1e2-48ae-901f-2729036e3aa7",
    "short_id":"f2eb56b0","date":"2026-08-13","date_source":"mtime","project":"-home-user-dev-demo","size":1},
   {"tool":"claude-code","path":"/x/aaaaaaaa.jsonl","session_id":"aaaaaaaa-0000-0000-0000-000000000000",
    "short_id":"aaaaaaaa","date":"2026-08-14","date_source":"first-event","project":"-home-user-dev-demo","size":1}]},
 "cursor": {"total": 2, "store_present": true, "sessions": [
   {"tool":"cursor","path":"/x/empty.jsonl","session_id":"441b4e4d-119d-4dc2-93a6-7061ec579ad2",
    "short_id":"441b4e4d","date":"2026-08-14","date_source":"mtime","project":"empty-window","size":1},
   {"tool":"cursor","path":"/x/work.jsonl","session_id":"441b4e4d-119d-4dc2-93a6-7061ec579ad2",
    "short_id":"441b4e4d","date":"2026-08-14","date_source":"mtime","project":"home-user-dev-watch-workface","size":1}]},
 "codex": {"total": 2, "store_present": true, "sessions": [
   {"tool":"codex","path":"/x/tui.jsonl","session_id":"01a001cc-b092-7d63-8f9d-9c9ed4e19f31",
    "short_id":"01a001cc","date":"2026-08-14","date_source":"session_meta","interactive":true,"size":1},
   {"tool":"codex","path":"/x/exec.jsonl","session_id":"019fe37e-0000-7000-8000-000000000000",
    "short_id":"019fe37e","date":"2026-08-14","date_source":"session_meta","interactive":false,"size":1}]}}}
EOF

python3 "$BW" --index "$TMP/index.json" --raw "$RAW" --out "$TMP/wl.json" >/dev/null 2>&1 \
    || fail "build-worklist exited non-zero"

python3 - "$TMP/wl.json" <<'PY' || exit 1
import json, sys
w = json.load(open(sys.argv[1]))
ids = {(r["tool"], r["short_id"], r.get("project")) for r in w["sessions"]}

assert ("claude-code", "f2eb56b0", "-home-user-dev-demo") not in ids, (
    "mtime-dated session deduped by DATE not identity — this is the 64-duplicate bug")
assert ("claude-code", "aaaaaaaa", "-home-user-dev-demo") in ids, "genuinely fresh session dropped"

assert ("cursor", "441b4e4d", "empty-window") not in ids, "imported cursor session not deduped"
assert ("cursor", "441b4e4d", "home-user-dev-watch-workface") in ids, (
    "cursor session deduped on UUID alone — the sibling project's session was lost")

assert ("codex", "01a001cc", None) in ids, "interactive codex session dropped"
assert not any(t == "codex" and s == "019fe37e" for t, s, _ in ids), (
    "non-interactive codex rollout kept")

assert w["dropped"]["already-imported"] == 2, w["dropped"]
assert w["dropped"]["non-interactive"] == 1, w["dropped"]
assert w["pending"] == 3, f"expected 3 pending, got {w['pending']}"
print("  ok: mtime-dated already-imported session deduped by identity")
print("  ok: cursor UUID collision kept as two distinct sessions")
print("  ok: non-interactive codex rollout excluded")
PY

ok "worklist dedup keys on identity, not on the filename date"
echo "ALL OK"
