#!/usr/bin/env bash
# test_vault_context_stack_hook.sh — stack-context.py, vault-context's second
# SessionStart hook, adds every synced stack page whose `paths` match a project
# file as SessionStart additionalContext, and prints nothing anywhere else.
#
# The stacks folder is a fixture (VAULT_CONTEXT_STACKS_DIR) and CLAUDE_CONFIG_DIR
# points into the scratch folder, so nothing here reads the real machine.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN="$ROOT/plugins/vault-context"
HOOK="$PLUGIN/scripts/stack-context.py"
SYNC="$PLUGIN/scripts/sync-stack-rules.py"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

[ -f "$HOOK" ] || fail "missing $HOOK"
[ -f "$SYNC" ] || fail "missing $SYNC"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

V="$WORK/vault"; ST="$V/Portfolio/stacks"; S="$WORK/stacks"
mkdir -p "$ST" "$S" "$WORK/cfg"
export CLAUDE_CONFIG_DIR="$WORK/cfg" VAULT_CONTEXT_STACKS_DIR="$S"
echo src > "$WORK/src.txt"

page() { # <slug> <paths-inline-list> <body>
    printf -- '---\nstack: %s\npaths: %s\nsources: ["%s"]\nchecked: 2026-11-17\n---\n%s' \
        "$1" "$2" "$WORK/src.txt" "$3" > "$ST/$1.md"
}
page rust   '["**/*.rs", "**/Cargo.toml"]' $'# Rust house rules\n\nUse the alpha way.\n'
page kotlin '["**/*.kt"]'                  $'# Kotlin house rules\n\nKotlin facts.\n'
python3 "$SYNC" --vault "$V" >/dev/null 2>&1 || fail "fixture sync"
[ -f "$S/vault-stack-rust.md" ] && [ -f "$S/vault-stack-kotlin.md" ] || fail "fixture sync wrote no copies to $S"

# hook <cwd> [stdin-json] — run the hook as Claude Code would, cwd in the input.
hook() {
    local cwd="$1" input="${2:-}"
    [ -n "$input" ] || input="$(jq -nc --arg c "$cwd" \
        '{session_id:"t", hook_event_name:"SessionStart", source:"startup", cwd:$c}')"
    (cd "$WORK" && printf '%s' "$input" | python3 "$HOOK")
}
context() { printf '%s' "$1" | jq -r '.hookSpecificOutput.additionalContext'; }

# Projects: a git project tracking src/lib.rs, a plain folder holding Cargo.toml,
# and a git project with no Rust file.
RP="$WORK/rust-proj"; mkdir -p "$RP/src/deep"
echo 'fn main() {}' > "$RP/src/lib.rs"; git -C "$RP" init -q && git -C "$RP" add -A
PP="$WORK/plain-proj"; mkdir -p "$PP"; echo '[package]' > "$PP/Cargo.toml"
NP="$WORK/none-proj"; mkdir -p "$NP"; echo hi > "$NP/README.md"
git -C "$NP" init -q && git -C "$NP" add -A

# --- 1. a project holding a matching file gets the page ---------------------------
out="$(hook "$RP")"; rc=$?
[ "$rc" -eq 0 ] || fail "hook exit $rc in a rust project"
printf '%s' "$out" | jq -e '.hookSpecificOutput.hookEventName == "SessionStart"' >/dev/null \
    || fail "output is not one SessionStart hookSpecificOutput object: $out"
[ "$(printf '%s' "$out" | jq -s 'length')" = 1 ] || fail "output is not exactly one JSON object: $out"
ctx="$(context "$out")"
[ "$ctx" = "$(cat "$S/vault-stack-rust.md")" ] \
    || fail "additionalContext is not the rust copy whole: $ctx"
case "$ctx" in *"vault-context:stack-rule source=rust "*) ;; *) fail "marker line missing: $ctx" ;; esac
case "$ctx" in *Kotlin*) fail "kotlin page added to a rust project: $ctx" ;; esac
ok "a git project tracking src/lib.rs gets the rust copy whole, marker included, and not kotlin"

out="$(hook "$RP/src/deep")"
[ "$(context "$out")" = "$(cat "$S/vault-stack-rust.md")" ] \
    || fail "a session in a subfolder did not get the page: $out"
ok "a session opened in a subfolder takes the git top level as the project root"

out="$(hook "$PP")"
[ "$(context "$out")" = "$(cat "$S/vault-stack-rust.md")" ] \
    || fail "a non-git folder holding Cargo.toml did not get the page: $out"
ok "a folder that is not a git repo but holds Cargo.toml gets the page"

# --- 2. no matching file → nothing -------------------------------------------------
out="$(hook "$NP")"; rc=$?
[ "$rc" -eq 0 ] || fail "hook exit $rc in a project with no matching file"
[ -z "$out" ] || fail "project with no matching file got output: $out"
ok "a project with no matching file gets no output at all"

echo 'class A' > "$NP/A.kt"; git -C "$NP" add -A
out="$(hook "$NP")"
ctx="$(context "$out")"
[ "$ctx" = "$(cat "$S/vault-stack-kotlin.md")" ] || fail "kotlin project did not get the kotlin page: $out"
rm "$NP/A.kt"; git -C "$NP" rm -q --cached A.kt
ok "the first matching file brings the page at the next session start"

# --- 3. two applying pages arrive in slug order ------------------------------------
echo 'class A' > "$RP/A.kt"; git -C "$RP" add -A
ctx="$(context "$(hook "$RP")")"
want="$(cat "$S/vault-stack-kotlin.md"; printf '\n'; cat "$S/vault-stack-rust.md")"
[ "$ctx" = "$want" ] || fail "two applying pages are not kotlin then rust, whole: $ctx"
ok "two applying pages arrive whole, in slug order"

# --- 4. the 9,500-character budget: a page that does not fit is named, not cut ------
big="$(python3 -c 'print("# Kotlin house rules\n\n" + ("k" * 79 + "\n") * 70, end="")')"
page kotlin '["**/*.kt"]' "$big"
big="$(python3 -c 'print("# Rust house rules\n\n" + ("r" * 79 + "\n") * 70, end="")')"
page rust '["**/*.rs", "**/Cargo.toml"]' "$big"
python3 "$SYNC" --vault "$V" >/dev/null 2>&1 || fail "fixture sync of the big pages"
out="$(hook "$RP")"
ctx="$(context "$out")"
n="$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext | length')"
[ "$n" -le 9500 ] || fail "additionalContext is $n characters, over 9,500"
case "$ctx" in "$(cat "$S/vault-stack-kotlin.md")"*) ;; *) fail "the first page is not whole at the start" ;; esac
case "$ctx" in *rrrrrrrrrr*) fail "part of the page that does not fit was added" ;; esac
line="$(printf '%s\n' "$ctx" | grep -F "$S/vault-stack-rust.md")" \
    || fail "the page that does not fit is not named with its path: $ctx"
[ "$(printf '%s\n' "$line" | wc -l)" -eq 1 ] || fail "the page that does not fit takes more than one line"
ok "a page that would pass 9,500 characters is named in one line with its path, never cut ($n chars)"
git -C "$RP" rm -q --cached A.kt; rm "$RP/A.kt"
page rust   '["**/*.rs", "**/Cargo.toml"]' $'# Rust house rules\n\nUse the alpha way.\n'
page kotlin '["**/*.kt"]'                  $'# Kotlin house rules\n\nKotlin facts.\n'
python3 "$SYNC" --vault "$V" >/dev/null 2>&1 || fail "fixture re-sync"

# --- 5. only marked files count ----------------------------------------------------
printf -- '---\npaths: ["**/*.rs"]\n---\n# Hand written\n' > "$S/vault-stack-zz.md"
printf 'not a stack\n' > "$S/notes.md"
ctx="$(context "$(hook "$RP")")"
[ "$ctx" = "$(cat "$S/vault-stack-rust.md")" ] || fail "an unmarked file was added: $ctx"
rm "$S/vault-stack-zz.md" "$S/notes.md"
ok "an unmarked vault-stack-*.md and other files in the stacks folder are ignored"

# --- 6. a broken input or a missing folder prints nothing and exits 0 --------------
out="$(hook "$RP" 'not json')"; rc=$?
[ "$rc" -eq 0 ] && [ -z "$out" ] || fail "bad stdin: exit $rc, output: $out"
out="$(hook "$WORK/no-such-dir")"; rc=$?
[ "$rc" -eq 0 ] && [ -z "$out" ] || fail "missing cwd: exit $rc, output: $out"
out="$(VAULT_CONTEXT_STACKS_DIR="$WORK/no-stacks" hook "$RP")"; rc=$?
[ "$rc" -eq 0 ] && [ -z "$out" ] || fail "missing stacks folder: exit $rc, output: $out"
ok "bad input, a missing cwd or a missing stacks folder → no output, exit 0"

# The default stacks folder is ${CLAUDE_CONFIG_DIR}/vault-stacks.
mkdir -p "$WORK/cfg/vault-stacks"; cp "$S/vault-stack-rust.md" "$WORK/cfg/vault-stacks/"
ctx="$(env -u VAULT_CONTEXT_STACKS_DIR bash -c 'cd "$1" && jq -nc --arg c "$2" "{cwd:\$c}" | python3 "$3"' _ \
    "$WORK" "$RP" "$HOOK" | jq -r '.hookSpecificOutput.additionalContext')"
[ "$ctx" = "$(cat "$S/vault-stack-rust.md")" ] || fail "default folder \$CLAUDE_CONFIG_DIR/vault-stacks not read: $ctx"
rm -r "$WORK/cfg/vault-stacks"
ok "without VAULT_CONTEXT_STACKS_DIR the hook reads \$CLAUDE_CONFIG_DIR/vault-stacks"

# --- 7. the hook writes nothing ----------------------------------------------------
snap() { (cd "$1" && find . -exec stat -c '%n %s %Y' {} + | sort | sha256sum); }
before="$(snap "$WORK"; snap "$PLUGIN")"
hook "$RP" >/dev/null; hook "$NP" >/dev/null
after="$(snap "$WORK"; snap "$PLUGIN")"
[ "$before" = "$after" ] || fail "the hook changed a file under the scratch folder or the plugin"
ok "the hook writes nothing (scratch folder and plugin tree unchanged)"

# --- 8. hooks.json registers it -----------------------------------------------------
jq -e '[.hooks.SessionStart[] | select(.matcher == "startup|resume|clear|compact|fork")
        | .hooks[] | select(.command | test("scripts/stack-context\\.py"))] | length == 1' \
    "$PLUGIN/hooks/hooks.json" >/dev/null || fail "hooks.json does not register stack-context.py on startup|resume|clear|compact|fork"
ok "hooks.json runs stack-context.py on SessionStart startup|resume|clear|compact|fork"

# --- one unreadable copy does not silence the others --------------------------
{ printf -- '---\npaths: ["**/*.rs"]\n---\n<!-- vault-context:stack-rule source=zbad sha256=0 -->\n'; printf 'bad \377\376 bytes\n'; } > "$S/vault-stack-zbad.md"
out="$(hook "$RP")"; rc=$?
[ "$rc" -eq 0 ] || fail "hook exit $rc with one undecodable copy"
context "$out" | grep -qF '# Rust house rules' || fail "an undecodable copy silenced the rust page: $out"
rm "$S/vault-stack-zbad.md"
ok "a copy that is not valid UTF-8 is skipped; the other applying pages still arrive"

echo "PASS: test_vault_context_stack_hook.sh"
