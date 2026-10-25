#!/usr/bin/env bash
# test_mirrors.sh — files this repo keeps in more than one place stay byte-identical.
#
# Each plugin installs on its own, so a shared definition is copied into every
# plugin that needs it rather than imported across plugins. A copy that drifts
# gives two plugins two answers to one question (which vault, which registry,
# which directory is a project, who may write now). This is the one list of those
# copies; a new copy belongs in a group here.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

FAILS=0
fail() { echo "FAIL: $*" >&2; FAILS=$((FAILS + 1)); }
ok()   { echo "  ok: $*"; }

# One group per line: the files that must be identical, space-separated.
GROUPS_LIST="
plugins/obsidian-wiki/scripts/resolve-vault.sh plugins/vault-context/scripts/resolve-vault.sh ports/cursor/obsidian-wiki/scripts/resolve-vault.sh
plugins/vault-context/scripts/lib/registry_path.py src/vault-portfolio/core/scripts/lib/registry_path.py
plugins/vault-context/scripts/lib/eligibility.sh src/vault-portfolio/core/scripts/lib/eligibility.sh
plugins/obsidian-wiki/scripts/vault_write_protocol.py ports/cursor/obsidian-wiki/scripts/vault_write_protocol.py src/vault-portfolio/core/scripts/lib/vault_write_protocol.py
"

n=0
while read -r first rest; do
    [ -n "$first" ] || continue
    n=$((n + 1))
    if [ ! -f "$ROOT/$first" ]; then fail "group $n: $first is missing"; continue; fi
    bad=0
    for other in $rest; do
        if [ ! -f "$ROOT/$other" ]; then fail "group $n: $other is missing"; bad=1
        elif ! cmp -s "$ROOT/$first" "$ROOT/$other"; then
            fail "group $n: $other differs from $first"; bad=1
        fi
    done
    [ "$bad" -eq 0 ] && ok "group $n: $(basename "$first") identical in $(( $(wc -w <<<"$rest") + 1 )) places"
done <<<"$GROUPS_LIST"

[ "$n" -gt 0 ] || fail "no mirror group listed"

# Every copy is in its group: a file sharing a grouped file's name anywhere in the
# repo, tracked or not, must be listed, or it can drift unseen. The built
# plugins/vault-portfolio tree is generated from src/ and checked against it by
# test_vault_portfolio_built.sh, and each host tree ports/<host>/vault-portfolio is
# generated the same way and checked by test_vault_portfolio_codex_built.sh (the
# build's --check, where a planning checkout is present), so none is listed here.
listed="$(tr ' ' '\n' <<<"$GROUPS_LIST" | sed '/^$/d' | sort -u)"
for name in $(xargs -n1 basename <<<"$listed" | sort -u); do
    while IFS= read -r copy; do
        case "$copy" in plugins/vault-portfolio/*|ports/*/vault-portfolio/*) continue ;; esac
        grep -qxF -- "$copy" <<<"$listed" || fail "$copy is a copy of $name in no mirror group"
    done < <(git -C "$ROOT" ls-files --cached --others --exclude-standard -- "*/$name" "$name")
done

[ "$FAILS" -eq 0 ] || { echo "$FAILS failure(s)" >&2; exit 1; }
echo "ALL OK"
