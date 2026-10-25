#!/usr/bin/env bash
# eligibility.sh — the "is this directory a project?" rule.
#
# vault-context writes a per-project sidecar. An *area directory* — a grouping
# folder that merely holds project repos — is not a project: a sidecar there
# duplicates every child repo's context into every session under the whole tree,
# on top of each child's own sidecar. This file is the single definition of that
# boundary, shared by the sidecar writer (write-context.sh) and the link check
# (validate-link.sh) so the two cannot drift apart.
#
# The rule, in order:
#
#   1. A directory with other *registered* projects beneath it is their grouping
#      folder, and never a project itself — whatever else is true about it.
#   2. Otherwise, a git repository is a project. This is the fallback for a
#      fresh repo nobody has registered yet.
#   3. Otherwise, a directory listed as a `path:` in the portfolio registry is
#      a project.
#
# Containment comes first because neither of the other two signals is reliable
# on its own:
#
#   - Registration is not evidence. A registry can carry an area directory as an
#     entry, and such an entry is exactly how a duplicate sidecar gets written.
#   - Being a git repo is not evidence either. A monorepo root holding several
#     registered projects is a repo, and its sidecar would duplicate most of each
#     child's pages into every session under it. A repo-first rule accepts it,
#     which is the same defect one directory over.
#
# The cost of ordering it this way is that a registered monorepo root whose
# subprojects are *also* registered is refused. That is the deliberate trade: a
# root of that shape is rare, while the shapes the rule refuses are the defect.

# Registry location: VAULT_CONTEXT_REGISTRY when set (tests point it at a fixture),
# else lib/registry_path.py, the one definition of where the registry lives. If
# that lookup cannot run (no python3), the location is unknown, it stays empty,
# and project_eligible fails closed: containment cannot be checked, so no
# directory is called a project. Treating "unknown" as "nothing registered" would
# quietly accept an area directory that holds registered projects.
if [ -z "${VAULT_CONTEXT_REGISTRY:-}" ]; then
    _elig_dir="${BASH_SOURCE[0]%/*}"; [ "$_elig_dir" != "${BASH_SOURCE[0]}" ] || _elig_dir=.
    VAULT_CONTEXT_REGISTRY="$(python3 "$_elig_dir/registry_path.py" 2>/dev/null)" || true
    unset _elig_dir
    [ -n "$VAULT_CONTEXT_REGISTRY" ] \
        || echo "vault-context: registry_path.py could not run (is python3 on PATH?)" >&2
fi

# _registry_paths — print every `path:` entry, normalized (no quotes, no
# trailing slash, no trailing comment), one per line. Silent when the registry
# is absent: an unreadable registry means "nothing is registered", not an error.
#
# `enabled:` is deliberately ignored. A disabled entry still marks a directory
# the user has called a project, which is what both predicates ask about — an
# archived project does not turn its parent back into a project, and it does not
# stop being a place a sidecar legitimately belongs. Revisit only if the registry
# starts using `enabled: false` to mean "this path is no longer a project at all".
_registry_paths() {
    [ -f "$VAULT_CONTEXT_REGISTRY" ] || return 0
    awk '
        {
            line = $0
            sub(/^[[:space:]]*-?[[:space:]]*/, "", line)
            if (line !~ /^path:[[:space:]]*/) next
            sub(/^path:[[:space:]]*/, "", line)
            sub(/[[:space:]]+#.*$/, "", line)
            sub(/[[:space:]]+$/, "", line)
            gsub(/^\042|\042$/, "", line)
            gsub(/^\047|\047$/, "", line)
            sub(/\/+$/, "", line)
            if (line != "") print line
        }
    ' "$VAULT_CONTEXT_REGISTRY"
}

# project_registered <abs-dir> — 0 iff <abs-dir> is a registry entry.
# Compared as strings, never as patterns: a project path can contain glob or
# regex metacharacters and must not become one.
project_registered() {
    local dir="${1%/}" p
    while IFS= read -r p; do
        [ "$p" = "$dir" ] && return 0
    done < <(_registry_paths)
    return 1
}

# project_contains_registered <abs-dir> — 0 iff a *different* registered project
# lives under <abs-dir>. The quoted "$dir" in the case pattern keeps the
# comparison literal; `?*` requires at least one path component below it, so a
# directory never contains itself.
project_contains_registered() {
    local dir="${1%/}" p
    while IFS= read -r p; do
        case "$p" in "$dir"/?*) return 0 ;; esac
    done < <(_registry_paths)
    return 1
}

# project_is_repo <abs-dir> — 0 iff <abs-dir> is a git repo root.
# `-e`, not `-d`: a linked worktree's .git is a file, not a directory.
project_is_repo() {
    [ -e "${1%/}/.git" ]
}

# project_eligible <abs-dir> — 0 iff vault-context may write a sidecar here.
project_eligible() {
    [ -n "$VAULT_CONTEXT_REGISTRY" ] || return 1
    project_contains_registered "$1" && return 1
    project_is_repo "$1" && return 0
    project_registered "$1" && return 0
    return 1
}

# area_directory_message <abs-dir> — the refusal text. Names the registry so the
# user can see what the verdict was made from, and points at the two ways out.
area_directory_message() {
    if [ -z "$VAULT_CONTEXT_REGISTRY" ]; then
        printf '%s\n' \
"vault-context: cannot tell whether $1 is a project. Nothing was written." \
"" \
"The portfolio registry could not be located: lib/registry_path.py did not run" \
"(is python3 on PATH?). Without the registry, a directory holding registered" \
"projects cannot be told apart from a project, so none is accepted."
        return 0
    fi
    printf '%s\n' \
"vault-context: $1 is an area directory — not a project. Nothing was written." \
"" \
"A directory counts as a project when it is a git repository, or when it is" \
"listed as a \`path:\` in $VAULT_CONTEXT_REGISTRY" \
"with no other registered project beneath it. This one is neither, so it looks" \
"like a grouping folder holding project repos — a sidecar here would duplicate" \
"every child project's context into every session under the tree." \
"" \
"Run /vault-context:link or /vault-context:refresh from the child project" \
"instead. If this really is a project, git init it (or, if the registry lists" \
"it only by mistake, fix that through /vault-portfolio), then re-run."
}
