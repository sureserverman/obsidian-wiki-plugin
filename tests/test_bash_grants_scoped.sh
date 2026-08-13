#!/usr/bin/env bash
# test_bash_grants_scoped.sh — no skill or agent may hold an unscoped Bash grant.
#
# Regression: the 2026-08-13 sec-audit run (sec-audit 1.36.3) raised two HIGH
# findings (CWE-77) for `allowed-tools: Read, Glob, Grep, Bash` on scan-sessions
# and `tools: … Bash` on the vault-scanner agent — components whose documented
# job is enumerating and sampling raw session transcripts from five external AI
# tools. Untrusted input plus an unrestricted shell grant is the hazard; two
# MEDIUMs of the same shape sat behind them (review-captures, gaps).
#
# A bare `Bash` token in a tools list is what this rejects. `Bash(cmd:*)` —
# argument-filtered — is fine, and so is declaring no Bash at all.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

CHECKED=0
BAD=0

# Frontmatter tool declarations: `allowed-tools:` in skills/commands, `tools:` in
# agents. Both accept the same Bash(cmd:*) scoping syntax.
while IFS= read -r f; do
    line="$(grep -m1 -E '^(allowed-tools|tools):' "$f" 2>/dev/null)" || continue
    [ -n "$line" ] || continue
    CHECKED=$((CHECKED + 1))

    # Strip every scoped grant, then look for a surviving bare `Bash` token.
    stripped="$(printf '%s' "$line" | sed -E 's/Bash\([^)]*\)//g')"
    if printf '%s' "$stripped" | grep -qE '(^|[,[:space:]"'"'"'[])Bash([,[:space:]"'"'"'\]]|$)'; then
        echo "  UNSCOPED: ${f#./}" >&2
        echo "            $line" >&2
        BAD=$((BAD + 1))
    fi
done < <(find plugins -type f \( -name 'SKILL.md' -o -path '*/agents/*.md' -o -path '*/commands/*.md' \) | sort)

[ "$CHECKED" -gt 0 ] || fail "no tool declarations found — did the frontmatter keys change?"
[ "$BAD" -eq 0 ] || fail "$BAD component(s) declare an unscoped Bash grant"
ok "all $CHECKED tool declaration(s) scope Bash or omit it"

# Guard the four the audit named, by path, so a future rewrite cannot quietly
# drop back to a blanket grant without this test naming the file.
for f in \
    plugins/obsidian-wiki/skills/scan-sessions/SKILL.md \
    plugins/obsidian-wiki/agents/vault-scanner.md \
    plugins/obsidian-wiki/skills/review-captures/SKILL.md \
    plugins/obsidian-wiki/skills/gaps/SKILL.md
do
    [ -f "$f" ] || fail "$f is gone — update this test if it moved"
    grep -qE '^(allowed-tools|tools):.*Bash\(' "$f" \
        || fail "$f no longer declares any scoped Bash grant"
done
ok "the four components named by the audit still carry scoped grants"

# scan-sessions genuinely needs these to do its job; if a future edit trims them
# the skill breaks at runtime rather than failing here, so assert them.
for cmd in bash find sqlite3; do
    grep -qE "Bash\($cmd:" plugins/obsidian-wiki/skills/scan-sessions/SKILL.md \
        || fail "scan-sessions lost Bash($cmd:*), which its discovery steps require"
done
ok "scan-sessions retains bash/find/sqlite3 — the commands its Step 2 documents"

echo "ALL OK"
