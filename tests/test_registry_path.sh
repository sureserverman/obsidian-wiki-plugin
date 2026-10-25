#!/usr/bin/env bash
# test_registry_path.sh — vault-context has one definition of where the
# portfolio registry lives (plugins/vault-context/scripts/lib/registry_path.py),
# and both readers use it.
#
# The order under test:
#   1. the `registry` key in ~/.config/obsidian-wiki/config.json
#   2. ~/.claude/projects-registry.yaml, if it exists
#   3. ~/.config/obsidian-wiki/projects-registry.yaml
#
# Each level runs in its own throwaway HOME under `env -i`, so nothing here
# reads the machine's real registry. For each level the test checks the path
# registry_path.py prints, the default eligibility.sh picks up, and the registry
# match-index.py actually reads — observed through its self-integration
# guarantee: a zero-score `Portfolio/<area>/<slug>/integration.md` page surfaces
# only when the registry maps cwd to <slug>. A lower level that would win if the
# order were wrong carries a decoy slug, so the wrong file cannot pass.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$ROOT/plugins/vault-context/scripts"
REGPATH="$SCRIPTS/lib/registry_path.py"
ELIG="$SCRIPTS/lib/eligibility.sh"
MATCH="$SCRIPTS/match-index.py"

FAILS=0
fail() { echo "FAIL: $*" >&2; FAILS=$((FAILS + 1)); }
ok()   { echo "  ok: $*"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# hermetic <home> <cmd...> — run with nothing from the caller's environment
# except PATH, and HOME pointed at the throwaway one.
hermetic() { local h="$1"; shift; env -i HOME="$h" PATH="$PATH" "$@"; }

# new_home <name> — a fresh HOME holding one project dir; prints the HOME path.
new_home() {
    local h="$WORK/$1"
    mkdir -p "$h/dev/apps/example-app"
    printf '%s\n' "$h"
}

# write_registry <file> <project-dir> <slug>
write_registry() {
    mkdir -p "$(dirname "$1")"
    cat > "$1" <<YAML
version: 1
projects:
  - path: $2
    name: $3
    enabled: true
YAML
}

# One index for every case: five pages that score on the signal `alpha`, and two
# integration pages that score zero (no overlap, no date), so they appear only
# through the self-integration guarantee.
INDEX="$WORK/index.md"
{
    echo "# Index — generated on 2026-01-01"
    echo
    echo "## Patterns/"
    for i in 1 2 3 4 5; do
        echo
        echo "### [[Alpha Page $i]]"
        echo "- path: Patterns/Alpha Page $i.md"
        echo "- tags: alpha"
    done
    echo
    echo "## Portfolio Integrations/"
    for slug in example-app decoy-app; do
        echo
        echo "### [[$slug integration]]"
        echo "- path: Portfolio/apps/$slug/integration.md"
    done
} > "$INDEX"

# match_slug <home> <project-dir> — the integration slug match-index.py surfaced
# from <project-dir> as cwd, or empty.
match_slug() {
    ( cd "$2" && echo alpha | hermetic "$1" python3 "$MATCH" "$INDEX" ) \
        | sed -n 's#.*"Portfolio/apps/\([^/"]*\)/integration\.md".*#\1#p' | head -n1
}

# eligibility_default <home> — the registry eligibility.sh settles on, unset.
eligibility_default() {
    hermetic "$1" bash -c '. "$1"; printf "%s\n" "$VAULT_CONTEXT_REGISTRY"' _ "$ELIG"
}

# check_level <label> <home> <project-dir> <expected-path>
check_level() {
    local label="$1" h="$2" proj="$3" want="$4" got
    got="$(hermetic "$h" python3 "$REGPATH" 2>&1)"
    [ "$got" = "$want" ] && ok "$label: registry_path.py prints the expected path" \
        || fail "$label: registry_path.py printed '$got', expected '$want'"
    got="$(eligibility_default "$h")"
    [ "$got" = "$want" ] && ok "$label: eligibility.sh defaults to the same path" \
        || fail "$label: eligibility.sh defaulted to '$got', expected '$want'"
    got="$(match_slug "$h" "$proj")"
    [ "$got" = "example-app" ] && ok "$label: match-index.py reads that registry (slug example-app)" \
        || fail "$label: match-index.py surfaced slug '$got', expected 'example-app'"
}

# --- Level 1: config.json `registry` key beats both files --------------------
H1="$(new_home level1)"
P1="$(cd "$H1/dev/apps/example-app" && pwd -P)"
mkdir -p "$H1/.config/obsidian-wiki"
printf '{"registry": "~/custom/registry.yaml"}\n' > "$H1/.config/obsidian-wiki/config.json"
write_registry "$H1/custom/registry.yaml" "$P1" example-app
write_registry "$H1/.claude/projects-registry.yaml" "$P1" decoy-app
write_registry "$H1/.config/obsidian-wiki/projects-registry.yaml" "$P1" decoy-app
check_level "config key" "$H1" "$P1" "$H1/custom/registry.yaml"

# --- Level 2: legacy ~/.claude file beats the XDG file -----------------------
H2="$(new_home level2)"
P2="$(cd "$H2/dev/apps/example-app" && pwd -P)"
write_registry "$H2/.claude/projects-registry.yaml" "$P2" example-app
write_registry "$H2/.config/obsidian-wiki/projects-registry.yaml" "$P2" decoy-app
check_level "legacy file" "$H2" "$P2" "$H2/.claude/projects-registry.yaml"

# --- Level 3: XDG only — the behavior change ---------------------------------
# No legacy file. match-index.py hard-coding ~/.claude finds no slug here.
H3="$(new_home level3)"
P3="$(cd "$H3/dev/apps/example-app" && pwd -P)"
write_registry "$H3/.config/obsidian-wiki/projects-registry.yaml" "$P3" example-app
check_level "XDG only" "$H3" "$P3" "$H3/.config/obsidian-wiki/projects-registry.yaml"

# --- Malformed config.json falls through, as resolve-vault.sh does -----------
H4="$(new_home malformed)"
mkdir -p "$H4/.config/obsidian-wiki"
printf '{"registry": \n' > "$H4/.config/obsidian-wiki/config.json"
got="$(hermetic "$H4" python3 "$REGPATH" 2>/dev/null)"
[ "$got" = "$H4/.config/obsidian-wiki/projects-registry.yaml" ] \
    && ok "malformed config.json → falls through to the next level" \
    || fail "malformed config.json: registry_path.py printed '$got'"

# --- No python3 on PATH: eligibility.sh fails closed, and says why ---------------
# The hooks source eligibility.sh under `set -e`, where a failed command
# substitution inside an assignment is invisible. With no registry location,
# containment cannot be checked, so no directory may be called a project, and
# the refusal must name the cause. It never guesses a registry path itself:
# registry_path.py is the one definition of where the registry lives.
NOPY="$WORK/nopy-bin"; mkdir -p "$NOPY"; ln -s "$(command -v bash)" "$NOPY/bash"
H5="$(new_home nopython)"
mkdir -p "$H5/dev/apps/example-app/.git"
err="$WORK/nopy.err"
out="$(env -i HOME="$H5" PATH="$NOPY" bash -c 'set -eu; . "$1"
    if project_eligible "$2"; then echo eligible; else echo refused; area_directory_message "$2"; fi' \
        _ "$ELIG" "$H5/dev/apps/example-app" 2>"$err")"; rc=$?
[ "$rc" -eq 0 ] && [ "$(head -1 <<<"$out")" = refused ] \
    && ok "no python3: even a git repo is refused (containment cannot be checked)" \
    || fail "no python3: rc=$rc, verdict '$(head -1 <<<"$out")'"
grep -q 'python3' <<<"$out" && ok "no python3: the refusal names the missing python3" \
    || fail "no python3: the refusal does not say why: $out"
grep -q 'registry_path.py' "$err" && ok "no python3: the failed lookup is reported on stderr" \
    || fail "no python3: nothing on stderr names the failed lookup: $(cat "$err")"

# The link check, too, must not call a real project an area directory just because
# the registry is unknown: that finding tells the user to unlink it.
if command -v jq >/dev/null 2>&1; then
    NOPY_ALL="$WORK/nopy-all"; mkdir -p "$NOPY_ALL"
    for d in /usr/local/bin /usr/bin /bin; do
        for f in "$d"/*; do
            n="${f##*/}"; case "$n" in python*) continue ;; esac
            [ -e "$NOPY_ALL/$n" ] || ln -s "$f" "$NOPY_ALL/$n"
        done
    done
    mkdir -p "$H5/dev/apps/example-app/.claude"   # linked: it has a sidecar
    printf 'Vault: x | Index: y\n' > "$H5/dev/apps/example-app/.claude/vault-context.md"
    out="$(env -i HOME="$H5" PATH="$NOPY_ALL" bash "$ROOT/plugins/vault-context/scripts/validate-link.sh" \
            "$H5/dev/apps/example-app" --json 2>/dev/null)"
    rules="$(printf '%s' "$out" | jq -r '[.findings[].rule] | join(" ")' 2>/dev/null)"
    case " $rules " in
        *" link-area-directory "*) fail "no python3: validate-link.sh called a git project an area directory" ;;
        *" link-registry-unknown "*) ok "no python3: validate-link.sh reports the unknown registry, not an area directory" ;;
        *) fail "no python3: validate-link.sh findings were '$rules': $out" ;;
    esac
fi

# --- The override still wins in eligibility.sh -------------------------------
got="$(hermetic "$H2" VAULT_CONTEXT_REGISTRY="$WORK/fixture.yaml" \
        bash -c '. "$1"; printf "%s\n" "$VAULT_CONTEXT_REGISTRY"' _ "$ELIG")"
[ "$got" = "$WORK/fixture.yaml" ] && ok "VAULT_CONTEXT_REGISTRY override is kept" \
    || fail "VAULT_CONTEXT_REGISTRY override lost: got '$got'"

# --- The refusal points at the skill that edits the registry -----------------
# A registry entry made by mistake is fixed through vault-portfolio, so the
# area-directory message must name that skill and no retired one.
msg="$(hermetic "$H2" VAULT_CONTEXT_REGISTRY="$WORK/fixture.yaml" \
        bash -c '. "$1"; area_directory_message /some/area' _ "$ELIG")"
grep -qF '/vault-portfolio:portfolio' <<<"$msg" \
    && ! grep -qE 'planning:(portfolio|compass)' <<<"$msg" \
    && ok "area-directory refusal names /vault-portfolio:portfolio" \
    || fail "area-directory refusal does not name /vault-portfolio:portfolio: $msg"

[ "$FAILS" -eq 0 ] || { echo "$FAILS failure(s)" >&2; exit 1; }
echo "ALL OK"
