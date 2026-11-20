#!/usr/bin/env bash
# codex_pointer_followed.sh <slug> <sample-relative-path>
# codex_pointer_followed.sh --parse <slug> <stream.jsonl>
#
# Live check, not part of tests/run.sh (it sits outside the test_*.sh glob, so CI
# never runs it): does Codex, with vault-context's pointer block in its home AGENTS
# file, read the stack copy vault-stacks/<slug>.md before it edits a file the
# pointer's pattern matches?
#
# It runs against the installed Codex home (${CODEX_HOME:-~/.codex}), which must
# already hold that copy (run the sync first). It makes a scratch git project
# holding <sample-relative-path> and runs one `codex exec --json` there, asking for
# a small edit to that file and naming no stack page.
#
# Prints `<slug> FOLLOWED` and exits 0 only when the event stream holds a completed
# command that exited 0 and names vault-stacks/<slug>.md. A message, a reasoning
# note or a read of AGENTS.md that merely repeats the pointer line does not count;
# neither does a read that failed or never finished. Otherwise nothing goes to
# stdout, the reason goes to stderr, the scratch folder (with the transcript) is
# kept and named, and the exit is 1. Exit 2 on usage, a missing program or copy, a
# stream that cannot be read, or one holding no Codex run (no `thread.started`
# event): a run that never started is not a pointer ignored.
#
# --parse decides from a saved stream, with no model call (tests/test_vault_context_live_parsers.sh).
set -u

usage() { echo "usage: $0 <slug> <sample-relative-path> | --parse <slug> <stream.jsonl>" >&2; exit 2; }

check_slug() {
    case "$1" in ''|*[!a-z0-9-]*) echo "codex_pointer_followed: bad slug: $1" >&2; exit 2 ;; esac
}

decide() { # <slug> <stream.jsonl>
    python3 - "$1" "$2" <<'EOF'
import json, re, sys
slug, stream = sys.argv[1], sys.argv[2]
copy = re.compile(r"vault-stacks/" + re.escape(slug) + r"\.md(?![A-Za-z0-9._-])")
named = 0
started = followed = False
for line in open(stream, errors="replace").read().splitlines():
    try:
        ev = json.loads(line)
    except ValueError:
        continue
    if isinstance(ev, dict) and ev.get("type") == "thread.started":
        started = True
    if not isinstance(ev, dict) or ev.get("type") != "item.completed":
        continue
    item = ev.get("item")
    if not isinstance(item, dict) or item.get("type") != "command_execution":
        continue
    if not copy.search(str(item.get("command") or "")):
        continue
    named += 1
    if item.get("status") == "completed" and item.get("exit_code") == 0:
        followed = True
if not started:
    # Not a Codex run (empty, crashed before starting, or another tool's shape): a
    # miss here would be read as Codex ignoring the pointer, so refuse instead.
    print("codex_pointer_followed: the stream holds no Codex run (no thread.started event)",
          file=sys.stderr)
    sys.exit(2)
if followed:
    print(f"{slug} FOLLOWED")
    sys.exit(0)
if named:
    print(f"codex_pointer_followed: {named} command(s) named vault-stacks/{slug}.md "
          f"but none completed with exit 0", file=sys.stderr)
else:
    print(f"codex_pointer_followed: no completed command named vault-stacks/{slug}.md",
          file=sys.stderr)
sys.exit(1)
EOF
}

if [ "${1:-}" = "--parse" ]; then
    [ $# -eq 3 ] || usage
    check_slug "$2"
    [ -f "$3" ] || { echo "codex_pointer_followed: no such stream: $3" >&2; exit 2; }
    decide "$2" "$3"
    exit $?
fi

[ $# -eq 2 ] || usage
slug="$1"; sample="$2"
check_slug "$slug"
case "$sample" in ''|/*|*..*) echo "codex_pointer_followed: sample must be a relative path inside the project: $sample" >&2; exit 2 ;; esac
command -v codex >/dev/null 2>&1 || { echo "codex_pointer_followed: codex is not installed" >&2; exit 2; }
home="${CODEX_HOME:-$HOME/.codex}"
[ -f "$home/vault-stacks/$slug.md" ] \
    || { echo "codex_pointer_followed: no copy at $home/vault-stacks/$slug.md; run the sync first" >&2; exit 2; }

work="$(mktemp -d)"
proj="$work/project"
mkdir -p "$proj/$(dirname "$sample")"
case "$sample" in
    *.rs) printf 'pub fn add(a: i32, b: i32) -> i32 {\n    a + b\n}\n' > "$proj/$sample" ;;
    *)    printf 'sample file for the %s check\n' "$slug" > "$proj/$sample" ;;
esac
git -C "$proj" init -q && git -C "$proj" add -A >/dev/null 2>&1

prompt="Add a one-line comment at the top of $sample saying what the file is for. Change nothing else."
codex exec --json --skip-git-repo-check --sandbox workspace-write -C "$proj" "$prompt" \
    </dev/null > "$work/stream.jsonl" 2> "$work/codex.err" || true

decide "$slug" "$work/stream.jsonl"; rc=$?
if [ "$rc" = 0 ]; then
    rm -rf "$work"
    exit 0
fi
echo "codex_pointer_followed: transcript kept: $work/stream.jsonl (stderr: $work/codex.err)" >&2
exit "$rc"
