#!/usr/bin/env bash
# Matrix chat contract must validate the only supported record shapes and reject unknown ones.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VALIDATOR="$ROOT/plugins/obsidian-wiki/scripts/validate-chat.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "  ok: $*"; }

[ -f "$VALIDATOR" ] || fail "validate-chat.py missing"
[ -f "$ROOT/plugins/obsidian-wiki/commands/import-chat.md" ] || fail "import-chat command missing"
[ -f "$ROOT/plugins/obsidian-wiki/commands/review-chat.md" ] || fail "review-chat command missing"
[ -f "$ROOT/docs/workflows/WF-CHAT-IMPORT.md" ] || fail "import workflow missing"
[ -f "$ROOT/docs/workflows/WF-CHAT-PUBLISH.md" ] || fail "publish workflow missing"

cat >"$TMP/revision.json" <<'EOF'
{"schema_version":1,"source_id":"mr-test","archive_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","revision_id":"rev-test","events":[{"event_key":"ev_one","occurred_at":"2024-01-01T00:00:00Z","kind":"message","availability":"available","protected_locator_ref":"pl_one"}]}
EOF

python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); from chat_records import event, revision; r = revision("mr-test", "a" * 64, "rev-builder", [event("private-event", "2024-01-01T00:00:00Z")]); assert r["events"][0]["event_key"].startswith("ev_") and r["events"][0]["protected_locator_ref"].startswith("pl_")' "$ROOT/plugins/obsidian-wiki/scripts" \
  || fail "fixture builders did not produce opaque records"
ok "fixture builders produce opaque records"

python3 "$VALIDATOR" --revision "$TMP/revision.json" --json >"$TMP/out" \
  || fail "valid revision was rejected"
jq -e '.ok == true and .mode == "revision"' "$TMP/out" >/dev/null \
  || fail "valid revision did not produce a successful revision verdict"
ok "valid revision is accepted"

cat >"$TMP/unknown.json" <<'EOF'
{"schema_version":1,"source_id":"mr-test","archive_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","revision_id":"rev-test","events":[{"event_key":"ev_one","occurred_at":"2024-01-01T00:00:00Z","kind":"unsupported","availability":"available","protected_locator_ref":"pl_one"}]}
EOF

if python3 "$VALIDATOR" --revision "$TMP/unknown.json" --json >"$TMP/out" 2>&1; then
  fail "unknown event shape was accepted"
fi
jq -e '.ok == false and (.errors | join(" ") | contains("unsupported kind"))' "$TMP/out" >/dev/null \
  || fail "unknown-shape refusal was not explicit"
ok "unknown event shape is refused explicitly"

echo "ALL OK"
