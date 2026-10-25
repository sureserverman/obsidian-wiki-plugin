#!/usr/bin/env bash
# test_cursor_install_plugins.sh — ports/cursor/install.sh takes one optional plugin name.
#
# Four things hold:
#   1. With no name, the installer does what it did before it took one: its --dry-run
#      (and a real run's) stdout, stderr, exit status and installed tree equal those of
#      the pre-change script. That script is embedded below, and checked against the
#      commit it came from whenever this clone holds that commit.
#   2. With vault-portfolio, the target is $CURSOR_PLUGIN_LOCAL_ROOT/vault-portfolio,
#      synced with --delete, and the obsidian-wiki target is left alone.
#   3. Any other name (bogus), or two names, exits 2 and installs nothing.
#   4. A symlinked target is refused, and the directory it points at is untouched.
#
# Everything runs in a scratch directory: HOME and CURSOR_PLUGIN_LOCAL_ROOT point there.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTALLER="$ROOT/ports/cursor/install.sh"
PRE_CHANGE_COMMIT=cc9cc07

FAILS=0
fail() { echo "FAIL: $*" >&2; FAILS=$((FAILS + 1)); }
ok() { echo "  ok: $*"; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pre_change_installer() {
    cat <<'PRE_CHANGE_INSTALLER'
#!/usr/bin/env bash
# install.sh — copy the Cursor port into Cursor's local plugin root.
#
#   bash ports/cursor/install.sh            # sync ports/cursor/obsidian-wiki -> ~/.cursor/plugins/local/obsidian-wiki
#   bash ports/cursor/install.sh --dry-run  # show what rsync would do
#
# Whole-directory sync with --delete, so a re-port removes files the port no
# longer ships. Refuses a symlinked target: an earlier-era symlink would make
# --delete act on the source tree. Nothing here touches ~/.cursor/hooks.json,
# ~/.cursor/skills, or any other plugin — this port has no hooks by design.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/obsidian-wiki"
dest="${CURSOR_PLUGIN_LOCAL_ROOT:-$HOME/.cursor/plugins/local}/obsidian-wiki"

dry=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) dry="--dry-run" ;;
        -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
        *) echo "install.sh: unknown argument: $arg" >&2; exit 2 ;;
    esac
done

[ -d "$src" ] || { echo "install.sh: $src not found (run from the repo, or fix the path)" >&2; exit 1; }
[ -d "$src/.cursor-plugin" ] || { echo "install.sh: $src is not a Cursor plugin dir (no .cursor-plugin/)" >&2; exit 1; }
command -v rsync >/dev/null 2>&1 || { echo "install.sh: rsync is required" >&2; exit 1; }
if [ -L "$dest" ]; then
    echo "install.sh: refusing: $dest is a symlink; remove it and re-run" >&2
    exit 1
fi

mkdir -p "$(dirname "$dest")"
rsync -a --delete ${dry:+"$dry"} --exclude '__pycache__' "$src/" "$dest/"
echo "obsidian-wiki Cursor port -> $dest${dry:+ (dry run)}"
PRE_CHANGE_INSTALLER
}

[ -f "$INSTALLER" ] || { echo "FAIL: $INSTALLER not found" >&2; exit 1; }
[ -d "$ROOT/ports/cursor/obsidian-wiki/.cursor-plugin" ] || {
    echo "FAIL: ports/cursor/obsidian-wiki is not a Cursor plugin dir" >&2; exit 1; }

# The embedded copy is the pre-change script, byte for byte, wherever history can say so.
if git -C "$ROOT" cat-file -e "$PRE_CHANGE_COMMIT:ports/cursor/install.sh" 2>/dev/null; then
    if cmp -s <(git -C "$ROOT" show "$PRE_CHANGE_COMMIT:ports/cursor/install.sh") <(pre_change_installer); then
        ok "the embedded pre-change installer equals $PRE_CHANGE_COMMIT:ports/cursor/install.sh"
    else
        fail "the embedded pre-change installer differs from $PRE_CHANGE_COMMIT:ports/cursor/install.sh"
    fi
else
    echo "  note: $PRE_CHANGE_COMMIT is not in this clone; comparing with the embedded copy only"
fi

# Two sandboxes, each a ports/cursor/ holding its installer and the real obsidian-wiki port;
# the new one also holds a minimal vault-portfolio port.
for side in old new; do
    mkdir -p "$tmp/$side/ports/cursor"
    cp -R "$ROOT/ports/cursor/obsidian-wiki" "$tmp/$side/ports/cursor/obsidian-wiki"
done
pre_change_installer > "$tmp/old/ports/cursor/install.sh"
cp "$INSTALLER" "$tmp/new/ports/cursor/install.sh"
vp="$tmp/new/ports/cursor/vault-portfolio"
mkdir -p "$vp/.cursor-plugin" "$vp/skills/vault-portfolio"
printf '{"name": "vault-portfolio"}\n' > "$vp/.cursor-plugin/plugin.json"
printf -- '---\nname: vault-portfolio\ndescription: fixture\n---\n' > "$vp/skills/vault-portfolio/SKILL.md"

# run <side> <home> <local-root or -> <args...>: the installer in a clean environment.
# Leaves $tmp/out, $tmp/err and $tmp/rc.
run() {
    local side="$1" home="$2" lroot="$3"; shift 3
    local envs=(PATH="$PATH" HOME="$home")
    [ "$lroot" = - ] || envs+=(CURSOR_PLUGIN_LOCAL_ROOT="$lroot")
    env -i "${envs[@]}" bash "$tmp/$side/ports/cursor/install.sh" "$@" >"$tmp/out" 2>"$tmp/err"
    echo $? >"$tmp/rc"
}
# snapshot <name>: keep the last run's stdout, stderr and status as <name>.*
snapshot() { cp "$tmp/out" "$tmp/$1.out"; cp "$tmp/err" "$tmp/$1.err"; cp "$tmp/rc" "$tmp/$1.rc"; }
same_run() {
    local what="$1"
    if cmp -s "$tmp/old.out" "$tmp/new.out" && cmp -s "$tmp/old.err" "$tmp/new.err" \
            && cmp -s "$tmp/old.rc" "$tmp/new.rc"; then
        ok "no name, $what: same stdout, stderr and exit status as before ($(cat "$tmp/new.out"))"
    else
        fail "no name, $what: the installer no longer behaves as before"
        diff <(cat "$tmp/old.out" "$tmp/old.err" "$tmp/old.rc") \
             <(cat "$tmp/new.out" "$tmp/new.err" "$tmp/new.rc") >&2
    fi
}

# --- 1. no name: today's behaviour, byte for byte ---------------------------------------
H="$tmp/home"
for case in "--dry-run|$tmp/local" "--dry-run|-"; do
    args="${case%%|*}"; lroot="${case#*|}"
    for side in old new; do
        rm -rf "$H" "$tmp/local"; mkdir -p "$H"
        run "$side" "$H" "$lroot" $args
        snapshot "$side"
    done
    same_run "$args (CURSOR_PLUGIN_LOCAL_ROOT ${lroot/#-/unset})"
done
expect="obsidian-wiki Cursor port -> $tmp/local/obsidian-wiki (dry run)"
rm -rf "$H" "$tmp/local"; mkdir -p "$H"
run new "$H" "$tmp/local" --dry-run
[ "$(cat "$tmp/out")" = "$expect" ] && [ "$(cat "$tmp/rc")" = 0 ] \
    && ok "no name, --dry-run names the obsidian-wiki target" \
    || fail "no name, --dry-run printed '$(cat "$tmp/out")' (status $(cat "$tmp/rc")), not '$expect'"

# A dry run over an installed copy carrying a stale file, then a real run that removes it.
for side in old new; do
    rm -rf "$H"; mkdir -p "$H"
    run "$side" "$H" - ; rm -f "$tmp/out"
    touch "$H/.cursor/plugins/local/obsidian-wiki/stale-file"
    run "$side" "$H" - --dry-run
    snapshot "$side"
    [ -e "$H/.cursor/plugins/local/obsidian-wiki/stale-file" ] \
        || fail "no name, --dry-run ($side) removed a file"
    run "$side" "$H" -
    cp "$tmp/out" "$tmp/$side.real.out"
    rm -rf "$tmp/$side.tree"; mv "$H/.cursor/plugins/local" "$tmp/$side.tree"
done
same_run "--dry-run over a copy with a stale file"
cp "$tmp/old.real.out" "$tmp/old.out"; cp "$tmp/new.real.out" "$tmp/new.out"
same_run "a real run"
if diff -r "$tmp/old.tree" "$tmp/new.tree" >/dev/null && [ ! -e "$tmp/new.tree/obsidian-wiki/stale-file" ] \
        && [ -f "$tmp/new.tree/obsidian-wiki/.cursor-plugin/plugin.json" ]; then
    ok "no name, a real run installs the same tree as before, stale file removed"
else
    fail "no name, a real run's installed tree differs from the pre-change installer's"
fi
for side in old new; do
    rm -rf "$H"; mkdir -p "$H"
    run "$side" "$H" "$tmp/local" --no-such-flag
    snapshot "$side"
done
same_run "an unknown flag"

# --- 2. vault-portfolio --------------------------------------------------------------------
L="$tmp/vp-local"
rm -rf "$H" "$L"; mkdir -p "$H"
run new "$H" "$L" vault-portfolio --dry-run
expect="vault-portfolio Cursor port -> $L/vault-portfolio (dry run)"
[ "$(cat "$tmp/out")" = "$expect" ] && [ "$(cat "$tmp/rc")" = 0 ] && [ ! -e "$L/vault-portfolio" ] \
    && ok "vault-portfolio --dry-run names \$CURSOR_PLUGIN_LOCAL_ROOT/vault-portfolio and writes nothing there" \
    || fail "vault-portfolio --dry-run printed '$(cat "$tmp/out")' (status $(cat "$tmp/rc")), not '$expect'"
run new "$H" "$L" vault-portfolio
touch "$L/vault-portfolio/stale-file"
run new "$H" "$L" vault-portfolio
if [ "$(cat "$tmp/rc")" = 0 ] && [ -f "$L/vault-portfolio/.cursor-plugin/plugin.json" ] \
        && [ -f "$L/vault-portfolio/skills/vault-portfolio/SKILL.md" ] \
        && [ ! -e "$L/vault-portfolio/stale-file" ] && [ ! -e "$L/obsidian-wiki" ] \
        && diff -r "$vp" "$L/vault-portfolio" >/dev/null; then
    ok "vault-portfolio syncs its port into \$CURSOR_PLUGIN_LOCAL_ROOT/vault-portfolio with --delete, and only there"
else
    fail "vault-portfolio did not install its port, alone and in full, at $L/vault-portfolio"
fi

# --- 3. a name outside obsidian-wiki|vault-portfolio, or two names ---------------------------
for args in "bogus" "bogus --dry-run" "vault-portfolio obsidian-wiki" "obsidian-wiki obsidian-wiki"; do
    rm -rf "$H" "$tmp/b-local"; mkdir -p "$H"
    run new "$H" "$tmp/b-local" $args
    if [ "$(cat "$tmp/rc")" = 2 ] && [ ! -e "$tmp/b-local" ] && [ -s "$tmp/err" ]; then
        ok "'$args' exits 2 and installs nothing"
    else
        fail "'$args' exited $(cat "$tmp/rc") (want 2), or wrote under the local root"
    fi
done

# --- 4. a symlinked target is refused ------------------------------------------------------
for name in vault-portfolio obsidian-wiki; do
    S="$tmp/sl-local"; E="$tmp/elsewhere"
    rm -rf "$S" "$E"; mkdir -p "$S" "$E"; touch "$E/keep"
    ln -s "$E" "$S/$name"
    args="$name"; [ "$name" = obsidian-wiki ] && args=""
    run new "$H" "$S" $args
    if [ "$(cat "$tmp/rc")" = 1 ] && grep -q 'refusing' "$tmp/err" \
            && [ "$(ls -A "$E")" = keep ] && [ -L "$S/$name" ]; then
        ok "${name}: a symlinked target is refused and what it points at is untouched"
    else
        fail "${name}: a symlinked target was not refused (status $(cat "$tmp/rc"))"
    fi
done

if [ "$FAILS" -ne 0 ]; then
    echo "$FAILS check(s) failed" >&2
    exit 1
fi
echo "ALL OK"
