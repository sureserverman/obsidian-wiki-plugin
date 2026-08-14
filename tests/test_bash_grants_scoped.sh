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

# scan-sessions is the sharpest case in the repo: its inputs are untrusted
# transcripts from five external tools. As of 0.9.1 discovery moved into the
# index-sessions hook, so it holds NO shell grant — in particular no
# Bash(sqlite3:*), whose .shell/.system dot-commands are RCE regardless of a
# read-only database URI.
grep -qE '^allowed-tools:.*Bash' plugins/obsidian-wiki/skills/scan-sessions/SKILL.md \
    && fail "scan-sessions reintroduced a Bash grant; discovery belongs in the hook"
grep -q 'sessions-index.json' plugins/obsidian-wiki/skills/scan-sessions/SKILL.md \
    || fail "scan-sessions no longer reads the hook-published session index"
ok "scan-sessions holds no shell grant and reads the published index"

# The hook and indexer that make that possible must stay present and wired.
grep -q 'index-sessions.sh' plugins/obsidian-wiki/hooks/hooks.json \
    || fail "index-sessions.sh is not wired into hooks.json"
[ -x plugins/obsidian-wiki/scripts/index-sessions.sh ] \
    || fail "index-sessions.sh missing or not executable"
[ -f plugins/obsidian-wiki/scripts/index-sessions.py ] \
    || fail "index-sessions.py missing"
ok "index-sessions hook + indexer present and wired"

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

# BL-027 end state: NO skill and NO agent holds any Bash grant. Every remaining
# shell call lives in a command, which runs only when the user types it — a skill
# can be triggered by natural language that an ingested source influenced, so this
# is the boundary that matters. Commands are allowed to hold grants; skills are not.
BAD_SKILL=0
while IFS= read -r f; do
    grep -qE '^(allowed-tools|tools):.*Bash' "$f" || continue
    echo "  SKILL/AGENT WITH SHELL: ${f#./}" >&2
    BAD_SKILL=$((BAD_SKILL + 1))
done < <(find plugins -type f \( -name 'SKILL.md' -o -path '*/agents/*.md' \) | sort)
[ "$BAD_SKILL" -eq 0 ] \
    || fail "$BAD_SKILL skill/agent file(s) hold a Bash grant; move the call to the command layer"
ok "no skill or agent holds a Bash grant — shell lives only in user-typed commands"

# ...and a command that runs a pipeline must actually declare what it uses, rather
# than inheriting silently. index.md and link.md both had no key at all before.
for c in plugins/obsidian-wiki/commands/lint.md plugins/obsidian-wiki/commands/index.md \
         plugins/vault-context/commands/link.md; do
    [ -f "$c" ] || fail "$c is gone — update this test if it moved"
    grep -qE '^allowed-tools:.*Bash\(' "$c" \
        || fail "$c runs a script but declares no scoped Bash grant"
done
ok "the three pipeline commands declare their own scoped grants"

echo "ALL OK"
