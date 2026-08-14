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

# An ABSENT key is broader than a bare `Bash` token: the component inherits the
# whole session tool set, Write and Edit included. The 2026-08-13 incremental
# audit raised 3 HIGH + 7 MEDIUM for exactly this, and an earlier version of
# this test could not see it — it only inspected files that already declared a
# key, so ten skills passed by having no declaration at all.
UNDECLARED=0
while IFS= read -r f; do
    grep -qE '^(allowed-tools|tools):' "$f" && continue
    echo "  NO DECLARATION: ${f#./}" >&2
    UNDECLARED=$((UNDECLARED + 1))
done < <(find plugins -type f \( -name 'SKILL.md' -o -path '*/agents/*.md' \) | sort)
[ "$UNDECLARED" -eq 0 ] || fail "$UNDECLARED skill/agent file(s) declare no tool set at all"
ok "every skill and agent declares an explicit tool set"

# Guard the four the audit named, by path, so a future rewrite cannot quietly
# drop back to a blanket grant without this test naming the file.
for f in \
    plugins/obsidian-wiki/skills/scan-sessions/SKILL.md \
    plugins/obsidian-wiki/agents/vault-scanner.md \
    plugins/obsidian-wiki/skills/review-captures/SKILL.md \
    plugins/obsidian-wiki/skills/gaps/SKILL.md
do
    [ -f "$f" ] || fail "$f is gone — update this test if it moved"
    # Scoped is acceptable; NO Bash at all is better. As of 0.9.0 the vault path
    # comes from a SessionStart hook via Read, so review-captures and gaps
    # declare no Bash whatsoever — asserting they still carry a grant would
    # punish the stronger outcome.
    line="$(grep -m1 -E '^(allowed-tools|tools):' "$f")"
    case "$line" in
        *"Bash("*) : ;;                       # scoped grant, fine
        *Bash*)   fail "$f declares an unscoped Bash grant" ;;
        *)        : ;;                        # no Bash at all, better
    esac
done
ok "the four components named by the audit scope Bash or declare none"

# scan-sessions genuinely needs these to do its job; if a future edit trims them
# the skill breaks at runtime rather than failing here, so assert them.
for cmd in bash find sqlite3; do
    grep -qE "Bash\($cmd:" plugins/obsidian-wiki/skills/scan-sessions/SKILL.md \
        || fail "scan-sessions lost Bash($cmd:*), which its discovery steps require"
done
ok "scan-sessions retains bash/find/sqlite3 — the commands its Step 2 documents"

# The 0.9.0 vault-path refactor: a skill whose only shell need WAS resolving the
# vault must now declare no Bash at all, and must tell the agent to Read the
# path the SessionStart hook publishes. If a future edit reintroduces the
# resolve-vault shell-out, the grant comes back with it — this catches that.
NO_SHELL_SKILLS="ask gaps import-session ingest merge rebuild-home related review-captures vault-schema-maintain"
for name in $NO_SHELL_SKILLS; do
    f="$(find plugins -path "*/skills/$name/SKILL.md" | head -1)"
    [ -n "$f" ] || fail "skill $name not found — update this test if it moved"
    grep -qE '^(allowed-tools|tools):.*Bash' "$f" \
        && fail "$f reintroduced a Bash grant; it should Read the published vault path"
    grep -q 'state/vault-path' "$f" \
        || fail "$f does not tell the agent to Read the hook-published vault path"
done
ok "the 9 vault-path-only skills declare no Bash and Read the published path"

# The hook that makes that possible must stay wired, or every one of them
# silently falls back to config.json and loses the $OBSIDIAN_VAULT_PATH override.
grep -q 'publish-vault-path.sh' plugins/obsidian-wiki/hooks/hooks.json \
    || fail "publish-vault-path.sh is not wired into hooks.json"
[ -x plugins/obsidian-wiki/scripts/publish-vault-path.sh ] \
    || fail "publish-vault-path.sh is missing or not executable"
ok "publish-vault-path.sh exists and is wired into SessionStart"

echo "ALL OK"
