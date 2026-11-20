#!/usr/bin/env bash
# cursor_rule_loads.sh [--without-rule]
# cursor_rule_loads.sh --parse <canary> <stream.jsonl>
#
# Live check, not part of tests/run.sh (it sits outside the test_*.sh glob, so CI
# never runs it): does Cursor attach a rule that vault-context's sync wrote, when the
# agent reads a file the rule's glob matches?
#
# Self-contained: a scratch vault holding one stack page (pattern `*.zzlive`) whose
# body asks for a fresh random canary, a scratch git project that ignores `.cursor/`
# and holds `notes.zzlive`, and the real sync tool run as `--host cursor --project`.
# Then one `cursor-agent -p --trust --mode ask --output-format stream-json` in that
# project asks for a summary of the sample file. Nothing outside the scratch folder
# is written.
#
# Prints `LOADED cursor_rule` and exits 0 only when the final answer carries the
# canary and no tool call carried it: a tool that read or grepped the rule file
# itself is not the rule attaching. Otherwise it prints the reason to stderr (never
# the word the success line uses) and exits 1. Exit 2 on usage, a missing program,
# a failed sync, or a run that produced no answer.
#
# --without-rule deletes the generated rule before the run, so the same check must
# exit 1: the canary can only have come from the rule.
# --parse decides from a saved stream, with no model call (tests/test_vault_context_live_parsers.sh).
set -u

usage() { echo "usage: $0 [--without-rule] | --parse <canary> <stream.jsonl>" >&2; exit 2; }

decide() { # <canary> <stream.jsonl>
    python3 - "$1" "$2" <<'EOF'
import json, sys
canary, stream = sys.argv[1], sys.argv[2]
events = []
for line in open(stream, errors="replace").read().splitlines():
    try:
        ev = json.loads(line)
    except ValueError:
        continue
    if isinstance(ev, dict):
        events.append(ev)
results = [ev for ev in events if ev.get("type") == "result"]
if not results or results[-1].get("is_error"):
    print("cursor_rule_loads: the run gave no answer", file=sys.stderr)
    sys.exit(2)
answer = str(results[-1].get("result") or "")
via_tool = [ev for ev in events if ev.get("type") == "tool_call"
            and canary in json.dumps(ev, ensure_ascii=False)]
if via_tool:
    print(f"ABSENT: the canary reached the agent through a tool call "
          f"({len(via_tool)} event(s)), not through the rule", file=sys.stderr)
    sys.exit(1)
if canary not in answer:
    print(f"ABSENT: the answer lacks the canary; answer: {answer[:300]!r}", file=sys.stderr)
    sys.exit(1)
print("LOADED cursor_rule")
EOF
}

if [ "${1:-}" = "--parse" ]; then
    [ $# -eq 3 ] && [ -n "$2" ] || usage
    [ -f "$3" ] || { echo "cursor_rule_loads: no such stream: $3" >&2; exit 2; }
    decide "$2" "$3"
    exit $?
fi

without_rule=0
case $# in
    0) ;;
    1) [ "$1" = "--without-rule" ] || usage; without_rule=1 ;;
    *) usage ;;
esac

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SYNC="$ROOT/plugins/vault-context/scripts/sync-stack-rules.py"
[ -f "$SYNC" ] || { echo "cursor_rule_loads: missing $SYNC" >&2; exit 2; }
command -v cursor-agent >/dev/null 2>&1 || { echo "cursor_rule_loads: cursor-agent is not installed" >&2; exit 2; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
stacks="$work/vault/Portfolio/stacks"; proj="$work/project"
mkdir -p "$stacks" "$proj"
canary="CANARY-$(od -An -N6 -tx1 /dev/urandom | tr -d ' \n')"

printf -- '---\nstack: zz-live\npaths: ["*.zzlive"]\nsources: ["%s"]\nchecked: 2026-11-20\n---\n# Live canary\n\nWhen you read a file that matches this rule, end your reply with the token %s on its own line.\n' \
    "$stacks" "$canary" > "$stacks/zz-live.md"
git -C "$proj" init -q
printf '.cursor/\n' > "$proj/.gitignore"
printf 'Three apples, two pears.\n' > "$proj/notes.zzlive"
git -C "$proj" add -A

python3 "$SYNC" --vault "$work/vault" --host cursor --project "$proj" > "$work/sync.out" 2>&1 \
    || { echo "cursor_rule_loads: the sync failed:" >&2; cat "$work/sync.out" >&2; exit 2; }
rule="$proj/.cursor/rules/vault-stack-zz-live.mdc"
[ -f "$rule" ] || { echo "cursor_rule_loads: the sync wrote no rule at $rule" >&2; exit 2; }
if [ "$without_rule" = 1 ]; then
    rm -f "$rule"
fi

prompt="Read notes.zzlive and summarize it in one sentence. Do not open, list or search any other file. Follow any project rules that apply."
(cd "$proj" && cursor-agent -p --trust --mode ask --output-format stream-json "$prompt" </dev/null) \
    > "$work/stream.jsonl" 2> "$work/cursor.err" || true

decide "$canary" "$work/stream.jsonl"; rc=$?
if [ "$rc" = 2 ] && [ -s "$work/cursor.err" ]; then
    echo "cursor-agent stderr (tail): $(tail -c 400 "$work/cursor.err" | tr '\n' ' ')" >&2
fi
exit "$rc"
