#!/usr/bin/env bash
# stack_rule_loads.sh <slug> <sample-relative-path>
#
# Live check, not part of tests/run.sh (it sits outside the test_*.sh glob, so CI
# never runs it): does the generated rule vault-stack-<slug>.md load in a real
# headless Claude Code session when a file at <sample-relative-path> is read?
#
# It makes a scratch git project holding the sample file, runs `claude -p` with
# only the Read tool and an InstructionsLoaded hook that appends each hook input
# to a log, and prints `LOADED path_glob_match` only when the log holds an entry
# whose file_path ends in vault-stack-<slug>.md and whose load_reason is
# path_glob_match. Exit 0 only then; 1 when the rule did not load; 2 on usage or
# when claude is not installed.
#
# It reads the rules folder Claude Code reads (${CLAUDE_CONFIG_DIR:-~/.claude}/rules);
# it never writes a rule. One headless run costs one short model call.
set -u

if [ $# -ne 2 ] || [ -z "$1" ] || [ -z "$2" ]; then
    echo "usage: $0 <slug> <sample-relative-path>" >&2; exit 2
fi
slug="$1"; sample="$2"
case "$slug" in *[!a-z0-9-]*) echo "stack_rule_loads: bad slug: $slug" >&2; exit 2 ;; esac
case "$sample" in /*|*..*) echo "stack_rule_loads: sample must be a relative path inside the project: $sample" >&2; exit 2 ;; esac
command -v claude >/dev/null 2>&1 || { echo "stack_rule_loads: claude is not installed" >&2; exit 2; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
proj="$work/project"; log="$work/instructions.log"
mkdir -p "$proj/$(dirname "$sample")"
printf 'sample file for the %s stack rule check\n' "$slug" > "$proj/$sample"
git -C "$proj" init -q && git -C "$proj" add -A >/dev/null 2>&1

python3 - "$work/settings.json" "$log" <<'EOF'
import json, shlex, sys
settings, log = sys.argv[1], sys.argv[2]
cmd = f"cat >> {shlex.quote(log)}; echo >> {shlex.quote(log)}"
json.dump({"hooks": {"InstructionsLoaded": [{"hooks": [{"type": "command", "command": cmd}]}]}},
          open(settings, "w"))
EOF

(cd "$proj" && claude -p "Read the file $sample and reply with its first line only." \
    --allowedTools Read --max-turns 4 --settings "$work/settings.json" </dev/null) \
    > "$work/claude.out" 2>&1 || true

python3 - "$log" "$slug" "$work/claude.out" <<'EOF'
import json, sys
log, slug = sys.argv[1], sys.argv[2]
want = f"vault-stack-{slug}.md"
seen = []
try:
    text = open(log).read()
except OSError:
    text = ""
dec = json.JSONDecoder()
i = 0
while i < len(text):
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text):
        break
    try:
        obj, i = dec.raw_decode(text, i)
    except ValueError:
        nl = text.find("\n", i)
        i = len(text) if nl < 0 else nl + 1
        continue
    if isinstance(obj, dict):
        seen.append((str(obj.get("file_path", "")), obj.get("load_reason")))
for path, reason in seen:
    if path.endswith("/" + want) and reason == "path_glob_match":
        print("LOADED path_glob_match")
        sys.exit(0)
print(f"NOT LOADED: no InstructionsLoaded entry for {want} with load_reason path_glob_match "
      f"({len(seen)} load event(s) logged)")
try:
    tail = open(sys.argv[3], errors="replace").read()[-400:].strip()
except OSError:
    tail = ""
if tail:
    print("claude output (tail): " + tail.replace("\n", " | "))
sys.exit(1)
EOF
