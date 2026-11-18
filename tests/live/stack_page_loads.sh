#!/usr/bin/env bash
# stack_page_loads.sh <slug> <sample-relative-path> [--plugin-dir DIR]
#
# Live check, not part of tests/run.sh (it sits outside the test_*.sh glob, so CI
# never runs it): does vault-context's session-start hook put the synced stack
# page vault-stack-<slug>.md into a real headless Claude Code session opened in a
# project that holds a file at <sample-relative-path>?
#
# It makes a scratch git project tracking the sample file and runs one
# `claude -p --output-format stream-json --verbose`, with no tools, asking for the
# first `# ` heading of that stack page as it stands in the session's context, or
# NONE. It prints `LOADED session_start_hook` and exits 0 only when the stream
# holds a SessionStart hook_response with exit code 0 whose stdout carries
# `vault-context:stack-rule source=<slug>`, and the answer holds the page's first
# `# ` heading (taken from that hook output). Exit 1 otherwise; 2 on usage or when
# claude is not installed.
#
# --plugin-dir DIR loads vault-context from DIR (a checkout's plugins/vault-context)
# instead of relying on the installed plugin. The hook reads the stacks folder the
# sync writes (${VAULT_CONTEXT_STACKS_DIR:-${CLAUDE_CONFIG_DIR:-~/.claude}/vault-stacks});
# this script never writes there. One headless run costs one short model call.
set -u

usage() { echo "usage: $0 <slug> <sample-relative-path> [--plugin-dir DIR]" >&2; exit 2; }

[ $# -eq 2 ] || [ $# -eq 4 ] || usage
slug="$1"; sample="$2"; plugin_dir=""
[ -n "$slug" ] && [ -n "$sample" ] || usage
if [ $# -eq 4 ]; then
    [ "$3" = "--plugin-dir" ] && [ -n "$4" ] || usage
    [ -d "$4" ] || { echo "stack_page_loads: --plugin-dir is not a folder: $4" >&2; exit 2; }
    plugin_dir="$(cd "$4" && pwd)"
fi
case "$slug" in *[!a-z0-9-]*) echo "stack_page_loads: bad slug: $slug" >&2; exit 2 ;; esac
case "$sample" in /*|*..*) echo "stack_page_loads: sample must be a relative path inside the project: $sample" >&2; exit 2 ;; esac
command -v claude >/dev/null 2>&1 || { echo "stack_page_loads: claude is not installed" >&2; exit 2; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
proj="$work/project"
mkdir -p "$proj/$(dirname "$sample")"
printf 'sample file for the %s stack page check\n' "$slug" > "$proj/$sample"
git -C "$proj" init -q && git -C "$proj" add -A >/dev/null 2>&1

prompt="Do not use any tools. Your context may hold a vault stack page added at session start, marked with an HTML comment 'vault-context:stack-rule source=$slug'. Reply with only the first line of that page that starts with '# ', exactly as written, or with NONE if no such page is in your context."

extra=()
[ -n "$plugin_dir" ] && extra=(--plugin-dir "$plugin_dir")
(cd "$proj" && claude -p "$prompt" --output-format stream-json --verbose --tools "" \
    "${extra[@]}" </dev/null) > "$work/stream.jsonl" 2> "$work/claude.err" || true

python3 - "$work/stream.jsonl" "$slug" "$work/claude.err" <<'EOF'
import json, sys
stream, slug, err = sys.argv[1], sys.argv[2], sys.argv[3]
marker = f"vault-context:stack-rule source={slug} "
events = []
try:
    lines = open(stream, errors="replace").read().splitlines()
except OSError:
    lines = []
for line in lines:
    try:
        ev = json.loads(line)
    except ValueError:
        continue
    if isinstance(ev, dict):
        events.append(ev)

heading = None
hooks_seen = 0
for ev in events:
    if not (ev.get("type") == "system" and ev.get("subtype") == "hook_response"
            and ev.get("hook_event") == "SessionStart"):
        continue
    hooks_seen += 1
    out = ev.get("stdout") or ""
    if ev.get("exit_code") != 0 or marker not in out:
        continue
    try:
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    except (ValueError, KeyError, TypeError):
        ctx = out
    seen_marker = False
    for l in ctx.split("\n"):
        if marker in l:
            seen_marker = True
        elif seen_marker and l.startswith("<!-- vault-context:stack-rule "):
            break
        elif seen_marker and l.startswith("# "):
            heading = l.strip()
            break
    if heading:
        break

answer = ""
for ev in events:
    if ev.get("type") == "result":
        answer = str(ev.get("result") or "")

if heading and heading in answer:
    print("LOADED session_start_hook")
    sys.exit(0)
if heading is None:
    print(f"NOT LOADED: no SessionStart hook_response with exit 0 carried {marker.strip()} "
          f"and a '# ' heading ({hooks_seen} SessionStart hook response(s) in the stream)")
else:
    print(f"NOT LOADED: the hook added the page but the answer lacks its heading {heading!r}; "
          f"answer: {answer[:200]!r}")
try:
    tail = open(err, errors="replace").read()[-400:].strip()
except OSError:
    tail = ""
if tail:
    print("claude stderr (tail): " + tail.replace("\n", " | "))
sys.exit(1)
EOF
