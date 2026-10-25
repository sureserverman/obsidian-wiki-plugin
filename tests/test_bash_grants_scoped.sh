#!/usr/bin/env bash
# test_bash_grants_scoped.sh — no skill or agent may hold an unscoped Bash grant.
#
# Regression: a security audit raised two HIGH
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
NO_SHELL_SKILLS="legacy-ask gaps import-session ingest merge rebuild-home related review-captures vault-schema-maintain"
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
         plugins/vault-context/commands/link.md \
         plugins/vault-portfolio/commands/portfolio.md plugins/vault-portfolio/commands/compass.md; do
    [ -f "$c" ] || fail "$c is gone — update this test if it moved"
    grep -qE '^allowed-tools:.*Bash\(' "$c" \
        || fail "$c runs a script but declares no scoped Bash grant"
done
ok "the five pipeline commands declare their own scoped grants"

# vault-portfolio's commands are user-typed only: a command the model may invoke on
# its own would carry its grants back to natural-language triggers. And their grants
# are EXACT read-only command lines. A grant stays in force for the whole turn,
# including while the skill reads vault-derived text, and a Bash rule with a `*`
# matches any text in its place (code.claude.com/docs/en/permissions, "Wildcard
# patterns"): `Bash(python3 …/portfolio-scan.py *)` pre-approved --add-all --write.
# Any line with arguments must go through the permission prompt instead. An earlier
# version of this check was a `case` glob, which let `…/skills/*/scripts/*.py` and a
# `../` traversal through; this compares against an explicit list.
VP_PLUGIN=plugins/vault-portfolio
expected_grants() {
    case "$1" in
        portfolio.md) cat <<'GRANTS'
Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/records-home.py --all-homes)
Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/portfolio/scripts/_config.py)
Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/portfolio/scripts/portfolio-rebuild.py)
Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/portfolio/scripts/portfolio-scan.py)
Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/portfolio/scripts/portfolio-unify.py)
GRANTS
        ;;
        compass.md) cat <<'GRANTS'
Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/compass/scripts/compass-scan.py)
GRANTS
        ;;
        *) return 1 ;;
    esac
}
VP_CMDS=0
while IFS= read -r c; do
    VP_CMDS=$((VP_CMDS + 1))
    base="$(basename "$c")"
    grep -qx 'disable-model-invocation: true' "$c" \
        || fail "$c lost disable-model-invocation: true"
    want="$(expected_grants "$base")" \
        || fail "$c has no expected grant list here — add one before shipping it"
    line="$(grep -m1 '^allowed-tools:' "$c")"
    grants="$(printf '%s\n' "$line" | grep -oE 'Bash\([^)]*\)' | LC_ALL=C sort)"
    [ -n "$grants" ] || fail "$c declares no Bash grant"
    # Nothing Bash-like may hide outside a parenthesised grant either.
    printf '%s' "$line" | sed -E 's/Bash\([^)]*\)//g' | grep -q 'Bash' \
        && fail "$c declares a Bash grant that is not of the form Bash(<exact line>)"
    while IFS= read -r g; do
        case "$g" in *'*'*) fail "$c grants a wildcard line: $g" ;; esac
        case "$g" in *'..'*) fail "$c grants a path with ..: $g" ;; esac
        script="$(printf '%s' "$g" | sed -nE 's/^Bash\(python3 \$\{CLAUDE_PLUGIN_ROOT\}\/([^ )]+\.py)( [^)]*)?\)$/\1/p')"
        [ -n "$script" ] || fail "$c grant is not python3 \${CLAUDE_PLUGIN_ROOT}/<script>.py: $g"
        [ -f "$VP_PLUGIN/$script" ] || fail "$c grants a script that does not exist: $VP_PLUGIN/$script"
    done <<< "$grants"
    if [ "$grants" != "$(printf '%s\n' "$want" | LC_ALL=C sort)" ]; then
        echo "  expected:" >&2; printf '    %s\n' "$want" >&2
        echo "  found:" >&2;    printf '    %s\n' "$grants" >&2
        fail "$c grants differ from the expected exact read-only lines"
    fi
done < <(find "$VP_PLUGIN/commands" -type f -name '*.md' | sort)
[ "$VP_CMDS" -eq 2 ] || fail "expected 2 vault-portfolio commands, found $VP_CMDS"
ok "vault-portfolio's commands are user-typed and grant only exact read-only lines"

# Lines with arguments are prompted, but the prompt shows what the model wrote, so the
# command must still refuse shell syntax in $ARGUMENTS before building a line from it.
grep -q 'Refuse unsafe text first' "$VP_PLUGIN/commands/portfolio.md" \
    || fail "portfolio.md lost its rule refusing shell syntax in \$ARGUMENTS"
ok "portfolio.md refuses shell syntax in its arguments"

# The opt-in ask command grants only the read executable, never admin/interpreters.
ask_grant="$(grep '^allowed-tools:' plugins/obsidian-wiki/commands/ask.md)"
case "$ask_grant" in
    'allowed-tools: Read, Glob, Grep, Write, Bash(${CLAUDE_PLUGIN_ROOT}/scripts/wiki-access.py *)') : ;;
    *) fail "ask command changed its exact dedicated read-executable grant" ;;
esac
ok "ask opt-in shell grant names only the dedicated read executable"

echo "ALL OK"
