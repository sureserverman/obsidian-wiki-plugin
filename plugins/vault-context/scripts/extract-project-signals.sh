#!/usr/bin/env bash
# extract-project-signals.sh — emit deduplicated, normalized tokens describing the
# project rooted at the current working directory. Output is one token per line on
# stdout, sorted and unique. Used by the link skill to match against a vault
# index.
#
# Sources, in order:
#   1. Project name: dir basename + `name` field from common manifests
#   2. Manifest dependencies (top 30 each): package.json, requirements.txt,
#      Cargo.toml, go.mod, pyproject.toml
#   3. Top-level directory names at depth 1 (excluding noise dirs)
#   4. README.md H1/H2 headings
#   5. Recent git commit subjects (last 50)
#
# Normalization: lowercase, alphanumeric+hyphen only, length >= 3, stopwords removed.

set -euo pipefail

cwd="$(pwd)"

NOISE_DIRS_RE='^(node_modules|\.git|target|dist|build|out|bin|obj|\.venv|venv|__pycache__|\.idea|\.vscode|\.next|\.nuxt|coverage|tmp|temp|cache|\.cache|vendor|deps)$'

STOPWORDS=" the a an is are was were be been being have has had do does did will would should could may might must can shall this that these those there here where when how why what who which not nor too very just only also more most some any all each every both few several about above below over under between through during before after into onto upon down off again further while because however therefore thus although though unless until whether either neither such "

# grep whose "no match" is a normal outcome, not a failure.
#
# Every call site below is the head of a pipeline, and the script runs under
# `set -o pipefail`: a bare grep that matches nothing exits 1, poisons the whole
# pipeline, and `set -e` then aborts collect_signals mid-way. The signals emitted
# before that point are still written, so the caller sees a short, plausible list
# rather than an error — a Cargo *workspace* manifest (no `[package] name`) cut
# real projects down to a single token, and every vault page then matched on the
# recency boost alone. Exit 2+ is a genuine grep error and still propagates.
grep_optional() {
    grep "$@" || [ $? -eq 1 ]
}

normalize_tokens() {
    tr '[:upper:]' '[:lower:]' \
        | tr -c 'a-z0-9-\n' ' ' \
        | tr -s ' ' '\n' \
        | awk -v stop=" $STOPWORDS " '
            length($0) >= 3 && index(stop, " " $0 " ") == 0 { print }
        '
}

collect_signals() {
    # 1. Project name
    printf '%s\n' "$(basename "$cwd")" | normalize_tokens

    for f in package.json pyproject.toml Cargo.toml go.mod; do
        [ -f "$cwd/$f" ] || continue
        case "$f" in
            package.json)
                python3 - <<'PY' 2>/dev/null | normalize_tokens
import json
try:
    with open("package.json") as fh:
        d = json.load(fh)
    n = d.get("name")
    if isinstance(n, str):
        print(n)
except Exception:
    pass
PY
                ;;
            pyproject.toml)
                grep_optional -E '^\s*name\s*=' "$cwd/$f" 2>/dev/null \
                    | head -n 1 \
                    | sed -E 's/.*=\s*"([^"]+)".*/\1/; s/.*=\s*'"'"'([^'"'"']+)'"'"'.*/\1/' \
                    | normalize_tokens
                ;;
            Cargo.toml)
                grep_optional -E '^\s*name\s*=' "$cwd/$f" 2>/dev/null \
                    | head -n 1 \
                    | sed -E 's/.*=\s*"([^"]+)".*/\1/' \
                    | normalize_tokens
                ;;
            go.mod)
                grep_optional -E '^module\s+' "$cwd/$f" 2>/dev/null \
                    | head -n 1 \
                    | awk '{print $2}' \
                    | tr '/' '\n' \
                    | normalize_tokens
                ;;
        esac
    done

    # 2. Manifest dependencies
    if [ -f "$cwd/package.json" ]; then
        python3 - <<'PY' 2>/dev/null | normalize_tokens
import json
try:
    with open("package.json") as fh:
        d = json.load(fh)
    keys = []
    for k in ("dependencies", "devDependencies", "peerDependencies"):
        v = d.get(k)
        if isinstance(v, dict):
            keys.extend(v.keys())
    for name in keys[:30]:
        if name.startswith("@") and "/" in name:
            scope, pkg = name.split("/", 1)
            print(scope.lstrip("@"))
            print(pkg)
        else:
            print(name)
except Exception:
    pass
PY
    fi

    if [ -f "$cwd/requirements.txt" ]; then
        head -n 30 "$cwd/requirements.txt" 2>/dev/null \
            | sed -E 's/[<>=!~;].*//; s/\[.*\]//; s/#.*//' \
            | normalize_tokens
    fi

    if [ -f "$cwd/Cargo.toml" ]; then
        awk '/^\[dependencies\]/{flag=1; next} /^\[/{flag=0} flag {print}' "$cwd/Cargo.toml" 2>/dev/null \
            | head -n 30 \
            | sed -E 's/^\s*([a-zA-Z0-9_-]+)\s*=.*/\1/' \
            | normalize_tokens
    fi

    if [ -f "$cwd/go.mod" ]; then
        awk '/^require\s*\(/{flag=1; next} /^\)/{flag=0} flag {print $1}' "$cwd/go.mod" 2>/dev/null \
            | head -n 30 \
            | tr '/' '\n' \
            | normalize_tokens
        grep_optional -E '^require\s+[^(]' "$cwd/go.mod" 2>/dev/null \
            | head -n 30 \
            | awk '{print $2}' \
            | tr '/' '\n' \
            | normalize_tokens
    fi

    if [ -f "$cwd/pyproject.toml" ]; then
        awk '/^\[(tool\.poetry\.)?dependencies\]/{flag=1; next} /^\[/{flag=0} flag {print}' "$cwd/pyproject.toml" 2>/dev/null \
            | head -n 30 \
            | sed -E 's/^\s*([a-zA-Z0-9_-]+)\s*=.*/\1/' \
            | normalize_tokens
    fi

    # 3. Top-level dirs
    find "$cwd" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null \
        | grep_optional -Ev "$NOISE_DIRS_RE" \
        | normalize_tokens

    # 4. README headings
    for readme in README.md readme.md Readme.md README.MD README; do
        [ -f "$cwd/$readme" ] || continue
        grep_optional -E '^#{1,2}\s+' "$cwd/$readme" 2>/dev/null \
            | sed -E 's/^#+\s+//' \
            | normalize_tokens
        break
    done

    # 5. Recent commit subjects
    if git -C "$cwd" rev-parse --show-toplevel >/dev/null 2>&1; then
        git -C "$cwd" log -50 --format=%s 2>/dev/null | normalize_tokens
    fi
}

collect_signals | sort -u
