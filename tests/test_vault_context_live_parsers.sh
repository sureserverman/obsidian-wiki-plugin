#!/usr/bin/env bash
# test_vault_context_live_parsers.sh — the two live checks under tests/live/ decide
# from a model's event stream. This test feeds each one canned streams through its
# --parse mode, so the decision is proven without a model call.
#
# Codex (codex_pointer_followed.sh): FOLLOWED only when a completed command that
# exited 0 names vault-stacks/<slug>.md. Quoting the AGENTS pointer line — in a
# message, in reasoning, or in the output of a read of AGENTS.md — is not following it.
#
# Cursor (cursor_rule_loads.sh): LOADED only when the answer carries the canary and
# no tool call carried it (a tool reading the rule file itself is not the rule
# attaching).
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CODEX="$ROOT/tests/live/codex_pointer_followed.sh"
CURSOR="$ROOT/tests/live/cursor_rule_loads.sh"
FX="$ROOT/tests/fixtures/vault-context-live"
CANARY="CANARY-FIXTURE-7Q2"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$CODEX" ] || fail "missing $CODEX"
[ -f "$CURSOR" ] || fail "missing $CURSOR"

# --- Codex ------------------------------------------------------------------------
out="$(bash "$CODEX" --parse rust "$FX/codex-followed.jsonl" 2>/dev/null)"; rc=$?
[ "$rc" = 0 ] || fail "codex: a completed read of the copy exited $rc"
[ "$out" = "rust FOLLOWED" ] || fail "codex: a completed read of the copy printed '$out'"
ok "codex: a completed read of vault-stacks/rust.md prints 'rust FOLLOWED'"

for case in quoted failed-read started-only other-copy; do
    out="$(bash "$CODEX" --parse rust "$FX/codex-$case.jsonl" 2>/dev/null)"; rc=$?
    [ "$rc" = 1 ] || fail "codex: $case exited $rc, want 1"
    [ -z "$out" ] || fail "codex: $case printed '$out' on stdout, want nothing"
done
ok "codex: quoting the pointer, a failed read, an unfinished read and another file print nothing and exit 1"

out="$(bash "$CODEX" --parse android-build "$FX/codex-other-copy.jsonl" 2>/dev/null)"; rc=$?
[ "$rc" = 0 ] && [ "$out" = "android-build FOLLOWED" ] \
    || fail "codex: the slug is not taken from the argument ($rc, '$out')"
ok "codex: the slug decides which copy counts"

bash "$CODEX" --parse 'Bad/Slug' "$FX/codex-followed.jsonl" >/dev/null 2>&1; rc=$?
[ "$rc" = 2 ] || fail "codex: a bad slug exited $rc, want 2"
bash "$CODEX" --parse rust "$FX/no-such.jsonl" >/dev/null 2>&1; rc=$?
[ "$rc" = 2 ] || fail "codex: a missing stream exited $rc, want 2"
ok "codex: a bad slug or a missing stream is a usage error (exit 2)"

# --- Cursor -----------------------------------------------------------------------
out="$(bash "$CURSOR" --parse "$CANARY" "$FX/cursor-loaded.jsonl" 2>/dev/null)"; rc=$?
[ "$rc" = 0 ] || fail "cursor: canary in the answer exited $rc"
[ "$out" = "LOADED cursor_rule" ] || fail "cursor: canary in the answer printed '$out'"
ok "cursor: the canary in the answer, through no tool, prints 'LOADED cursor_rule'"

for case in via-tool absent; do
    out="$(bash "$CURSOR" --parse "$CANARY" "$FX/cursor-$case.jsonl" 2>/dev/null)"; rc=$?
    [ "$rc" = 1 ] || fail "cursor: $case exited $rc, want 1"
    printf '%s' "$out" | grep -q LOADED && fail "cursor: $case printed '$out', which a grep for LOADED would pass"
done
ok "cursor: a canary that came through a tool, or no canary, exits 1 and never prints LOADED"

bash "$CURSOR" --parse "" "$FX/cursor-loaded.jsonl" >/dev/null 2>&1; rc=$?
[ "$rc" = 2 ] || fail "cursor: an empty canary exited $rc, want 2"
ok "cursor: an empty canary is a usage error (exit 2)"

echo "PASS: live-check parsers"
