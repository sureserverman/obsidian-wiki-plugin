#!/usr/bin/env bash
# test_vault_portfolio_portable.sh — vault-portfolio ships nothing tied to one
# machine or one owner's history.
#
# A generic sweep over src/vault-portfolio, plugins/vault-portfolio and every
# ports/<host>/vault-portfolio. It holds
# no names, only classes, and fails on any of:
#   home    an absolute home or mount path (/home/x, /Users/x, /mnt/x, /root, …)
#   email   an email address (example.* and .test/.invalid addresses excepted)
#   plugin  a <plugin>:<skill> id other than vault-portfolio:, planning:,
#           obsidian-wiki: or vault-context:
#   id      a backlog/decision/workflow/architecture id (DEC-12, GDEC-SEC-1,
#           BL-7, WF-3, ARCH-2, tagged DEC-XX-1) outside a *-format.md file,
#           where ids are the documented shape. NNN placeholders are fine.
# The second half plants each class in a temp tree and asserts the sweep
# catches it, so a class the sweep has stopped matching shows up here.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

FAILS=0
fail() { echo "FAIL: $*" >&2; FAILS=$((FAILS + 1)); }
ok()   { echo "  ok: $*"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

SWEEP="$WORK/sweep.py"
cat > "$SWEEP" <<'PY'
import os, re, sys

NAME = r"[A-Za-z0-9._-]+"
CLASSES = {
    "home": re.compile(r"(?<![\w.~-])(?:(?:/var)?/home/" + NAME + r"|/Users/" + NAME
                       + r"|/roo[t](?![\w-])|/mnt/" + NAME + r"|(?:/run)?/media/" + NAME
                       + r"|/Volumes/" + NAME + r")"),
    "email": re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*"
                        r"\.[A-Za-z]{2,})(?![^\W_])"),
    "id": re.compile(r"\b(?:(?:DEC|BL|WF|ARCH)-(?:[A-Z]{2,4}-)?\d+|GDEC-[A-Z]+-\d+)\b"),
}
EMAIL_OK = re.compile(r"(?:^|\.)(?:example\.(?:com|org|net)|[a-z0-9-]+\.(?:test|example|invalid))$")
ID = r"([a-z][a-z0-9-]*):([a-z][a-z0-9-]*)"
PLUGIN_RES = [
    re.compile(r"(?<![\w/.:-])/" + ID + r"(?![\w:])"),           # slash command
    re.compile(r"`" + ID + r"(?=[`\s(])"),                       # code span
    re.compile(r"[\"']" + ID + r"[\"']"),                        # quoted string
    re.compile(r"\b(?:Skill|Agent)\(\s*" + ID + r"(?![\w:])"),   # Skill()/Agent() call
]
OWN = {"vault-portfolio", "planning", "obsidian-wiki", "vault-context"}
NOT_PLUGIN = {"http", "https", "git", "file", "mailto", "data", "ssh", "sha256", "urn",
              "localhost", "std"}

hits = 0
for top in sys.argv[1:]:
    for dirpath, dirnames, files in os.walk(top):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".git"}]
        for f in sorted(files):
            path = os.path.join(dirpath, f)
            try:
                lines = open(path, encoding="utf-8").read().splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for n, line in enumerate(lines, 1):
                found = [c for c, rx in CLASSES.items() if c != "email" and rx.search(line)]
                if "id" in found and f.endswith("-format.md"):
                    found.remove("id")
                for m in CLASSES["email"].finditer(line):
                    if not EMAIL_OK.search(m.group(1)):
                        found.append("email")
                for rx in PLUGIN_RES:
                    for m in rx.finditer(line):
                        if m.group(1) not in OWN | NOT_PLUGIN:
                            found.append("plugin")
                for c in sorted(set(found)):
                    print(f"{c} {path}:{n}")
                    hits += 1
sys.exit(1 if hits else 0)
PY

sweep() { python3 -I "$SWEEP" "$@"; }

# --- The real trees ------------------------------------------------------------
trees=()
# Every host's output, by glob: a host added later is swept without editing this list.
for t in "$ROOT/src/vault-portfolio" "$ROOT/plugins/vault-portfolio" \
         "$ROOT"/ports/*/vault-portfolio "$ROOT/.agents/plugins"; do
    [ -d "$t" ] && trees+=("$t")
done
if [ "${#trees[@]}" -eq 0 ]; then
    fail "neither src/vault-portfolio nor plugins/vault-portfolio exists"
elif out="$(sweep "${trees[@]}")"; then
    ok "vault-portfolio source and build carry no machine or history shapes"
else
    fail "portability findings:"; printf '%s\n' "$out" >&2
fi

# --- Each class is caught, one regex branch per plant ---------------------------
# A fresh directory per plant and an exact-hit match, so one plant can never pass
# on a hit another plant made.
N=0
plant() {  # plant <class> <file name> <line>
    N=$((N + 1)); local d="$WORK/plant-$N"; mkdir -p "$d"; printf '%s\n' "$3" > "$d/$2"
    local out; out="$(sweep "$d")"
    if [ "$out" = "$1 $d/$2:1" ]; then ok "the sweep catches a planted $1: $3"
    else fail "planted $1 '$3': sweep printed '$out'"; fi
}
plant home   notes.md  'see /home/someone/dev/x'
plant home   notes.md  'see /var/home/someone/x'
plant home   notes.md  'see /Users/someone/x'
plant home   notes.md  'run as /root'
plant home   notes.md  'the vault is at /mnt/notes'
plant home   notes.md  'mounted at /media/disk'
plant home   notes.md  'mounted at /run/media/disk'
plant home   notes.md  'on /Volumes/disk'
plant email  notes.md  'mail someone@realmail.org'
plant plugin SKILL.md  'run /other-plugin:portfolio first'
plant plugin SKILL.md  'run `other-plugin:portfolio` first'
plant plugin SKILL.md  'the id is "other-plugin:portfolio"'
plant plugin SKILL.md  'call Skill(other-plugin:portfolio)'
plant id     SKILL.md  'decided in DEC-012'
plant id     SKILL.md  'parked as BL-140'
plant id     SKILL.md  'per WF-3'
plant id     SKILL.md  'per ARCH-2'
plant id     SKILL.md  'a tagged DEC-XX-001'
plant id     notes.md  'see GDEC-SEC-001'

# The documented exceptions stay quiet.
d="$WORK/quiet"; mkdir -p "$d"
printf '%s\n' 'cite as DEC-012' > "$d/decisions-format.md"
printf '%s\n' 'a DEC-NNN placeholder, `/vault-portfolio:portfolio`, `planning:executing-plans`' \
    'user@example.com and t@host.invalid' > "$d/SKILL.md"
if out="$(sweep "$d")"; then ok "format files, placeholders, own ids and reserved emails pass"
else fail "a documented exception was flagged:"; printf '%s\n' "$out" >&2; fi

[ "$FAILS" -eq 0 ] || { echo "$FAILS failure(s)" >&2; exit 1; }
echo "ALL OK"
