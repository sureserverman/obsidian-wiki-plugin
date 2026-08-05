#!/usr/bin/env bash
# eligibility.sh — the "is this directory a project?" rule.
#
# vault-context writes a per-project sidecar. An *area directory* — a grouping
# folder like ~/dev/ai-tools that merely holds project repos — is not a project:
# a sidecar there duplicates every child repo's context into every session under
# the whole tree, on top of each child's own sidecar. This file is the single
# definition of that boundary, shared by the write path (write-context.sh) and
# the detect path (validate-link.sh) so the two cannot drift apart.
#
# The rule, in order:
#
#   1. A git repository is a project. This is the fallback for a fresh repo
#      nobody has registered yet, and it is checked first so a genuine monorepo
#      root is never refused by rule 3.
#   2. A directory listed as a `path:` in the portfolio registry is a project…
#   3. …unless other registered projects live *beneath* it, which is what a
#      grouping folder looks like from the registry's point of view.
#
# Rule 3 exists because registration alone is not evidence: the registry can
# and does carry an area directory as an entry (~/dev/ai-tools was registered
# on 2026-06-17), and that entry is exactly how the duplicate sidecar this
# guard prevents got written. Deriving "area directory" from the containment
# relation instead means the guard stays correct while the registry is wrong,
# rather than inheriting its mistakes.

# Registry location. Overridable so tests can point at a fixture.
: "${VAULT_CONTEXT_REGISTRY:=${HOME}/.claude/projects-registry.yaml}"

# _registry_paths — print every `path:` entry, normalized (no quotes, no
# trailing slash, no trailing comment), one per line. Silent when the registry
# is absent: an unreadable registry means "nothing is registered", not an error.
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
    project_is_repo "$1" && return 0
    project_registered "$1" && ! project_contains_registered "$1" && return 0
    return 1
}

# area_directory_message <abs-dir> — the refusal text. Names the registry so the
# user can see what the verdict was made from, and points at the two ways out.
area_directory_message() {
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
"it only by mistake, fix that through /planning:portfolio), then re-run."
}
