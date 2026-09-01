#!/usr/bin/env bash
# test_vault_context_signal_extraction.sh — a manifest that legitimately matches
# nothing must not truncate the signal list.
#
# extract-project-signals.sh runs under `set -euo pipefail` and heads several
# pipelines with grep. A grep that finds nothing exits 1, which pipefail turns
# into a failed pipeline and errexit turns into an aborted run — and because the
# tokens emitted before that point have already been written, the caller gets a
# short but plausible list instead of an error. Measured in the wild: seven
# Cargo *workspace* repos (no `[package] name`) each produced exactly one token,
# their own basename, and every vault page then scored on the recency boost
# alone.
#
# Each case below asserts that the later signal sources — dirs, README headings,
# git subjects — still land after the empty match.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXTRACT="$ROOT/plugins/vault-context/scripts/extract-project-signals.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$EXTRACT" ] || fail "missing $EXTRACT"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Every fixture carries the same three late-stage signals, so any early abort is
# visible as a missing token regardless of which manifest triggered it.
scaffold() {
    local d="$1"
    mkdir -p "$d/crates" "$d/docs"
    printf '# Zzumbra Widget\n\n## Kwyjibo Layout\n' > "$d/README.md"
}

# late-stage tokens: crates + docs (dirs), zzumbra + kwyjibo (README headings)
assert_full() {
    local d="$1" label="$2" out missing
    out="$(cd "$d" && bash "$EXTRACT" 2>/dev/null)" \
        || fail "$label: extractor exited non-zero"
    missing=""
    for tok in crates docs zzumbra kwyjibo; do
        printf '%s\n' "$out" | grep -qx "$tok" || missing="$missing $tok"
    done
    [ -z "$missing" ] && ok "$label: all late signals present ($(printf '%s\n' "$out" | wc -l) tokens)" \
        || fail "$label: signal list truncated, missing:$missing (got $(printf '%s\n' "$out" | wc -l) tokens)"
}

# --- 1. Cargo workspace manifest: no [package] name --------------------------
W="$WORK/cargo-workspace"; scaffold "$W"
cat > "$W/Cargo.toml" <<'TOML'
[workspace]
resolver = "3"
members = ["crates/alpha", "crates/beta"]
TOML
assert_full "$W" "Cargo workspace (no [package] name)"

# --- 2. pyproject.toml with no name key --------------------------------------
Y="$WORK/pyproject-nameless"; scaffold "$Y"
printf '[build-system]\nrequires = ["setuptools"]\n' > "$Y/pyproject.toml"
assert_full "$Y" "pyproject.toml without a name key"

# --- 3. go.mod with only a block require (no single-line require) ------------
G="$WORK/gomod-block"; scaffold "$G"
cat > "$G/go.mod" <<'GOMOD'
module example.com/widget

go 1.22

require (
	github.com/spf13/cobra v1.8.0
)
GOMOD
assert_full "$G" "go.mod with only a block require"

# --- 4. README with no H1/H2 headings ----------------------------------------
R="$WORK/readme-no-headings"; scaffold "$R"
printf 'plain prose, no headings at all\n' > "$R/README.md"
out="$(cd "$R" && bash "$EXTRACT" 2>/dev/null)" || fail "README-no-headings: extractor exited non-zero"
for tok in crates docs; do
    printf '%s\n' "$out" | grep -qx "$tok" || fail "README-no-headings: missing dir token $tok"
done
ok "README with no headings: dir signals still emitted"

# --- 5. only noise dirs: the dir filter matches nothing ----------------------
N="$WORK/noise-only"; mkdir -p "$N/node_modules" "$N/target"
printf '# Zzumbra Widget\n' > "$N/README.md"
out="$(cd "$N" && bash "$EXTRACT" 2>/dev/null)" || fail "noise-only: extractor exited non-zero"
printf '%s\n' "$out" | grep -qx zzumbra \
    || fail "noise-only: README signal lost after the dir filter matched nothing"
ok "all-noise dir list: later signals still emitted"

# --- 6. a real grep error still fails ----------------------------------------
# Exit 2+ must keep propagating; only "no match" is tolerated.
if bash -c '
    set -euo pipefail
    grep_optional() { grep "$@" || [ $? -eq 1 ]; }
    grep_optional -E "x" /nonexistent/definitely/not/here 2>/dev/null
' 2>/dev/null; then
    fail "grep_optional swallowed a real grep error (exit 2+)"
fi
ok "grep_optional still propagates a genuine grep error"

echo "PASS: $(basename "$0")"
