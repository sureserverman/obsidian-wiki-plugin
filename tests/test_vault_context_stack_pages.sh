#!/usr/bin/env bash
# test_vault_context_stack_pages.sh — stack_pages.py reads a stack page and
# matches its `paths:` globs the way Claude Code matches a rule's `paths:`.
#
# Covers plugins/vault-context/scripts/lib/stack_pages.py:
#   glob_match   — the five pattern rows of the Claude Code memory docs table,
#                  plus {a,b} expansion and refusal of unsupported patterns
#   load_page    — a good page loads; every bad page is refused with the page
#                  path and the reason, never guessed at or truncated
#   applies      — a stack applies when any project file matches any pattern
#   project_files — git ls-files in a repo, a pruned walk outside one
#
# Every page is a fixture written under a temp dir, so the test says nothing
# about the machine it runs on.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$ROOT/plugins/vault-context/scripts/lib"

fail() { echo "FAIL: $*" >&2; exit 1; }

[ -f "$LIB/stack_pages.py" ] || fail "missing $LIB/stack_pages.py"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

LIB="$LIB" WORK="$WORK" python3 - <<'EOF' || fail "stack_pages cases failed (see above)"
import os
import subprocess
import sys

sys.path.insert(0, os.environ["LIB"])
sys.dont_write_bytecode = True
import stack_pages as sp

WORK = os.environ["WORK"]
failures = 0


def ok(msg):
    print(f"  ok: {msg}")


def bad(msg):
    global failures
    failures += 1
    print(f"FAIL: {msg}", file=sys.stderr)


def expect_match(pattern, path, want):
    try:
        got = sp.glob_match(pattern, path)
    except Exception as e:  # noqa: BLE001 - report, don't crash the run
        bad(f"glob_match({pattern!r}, {path!r}) raised {e!r}")
        return False
    if got != want:
        bad(f"glob_match({pattern!r}, {path!r}) = {got}, want {want}")
        return False
    return True


def row(pattern, hits, misses, label):
    good = all([expect_match(pattern, p, True) for p in hits]
               + [expect_match(pattern, p, False) for p in misses])
    if good:
        ok(label)


# --- the five rows of the Claude Code docs table ------------------------------
row("**/*.ts", ["a.ts", "src/a.ts", "src/x/y/a.ts"], ["a.tsx", "a.js", "src/a.ts.bak"],
    "**/*.ts matches .ts at any depth, top level included")
row("src/**/*", ["src/a", "src/x/y.rs", "src/x/y/z.md"], ["lib/a.rs", "src", "a/src/b.rs"],
    "src/**/* matches everything under src/ and nothing outside it")
row("*.md", ["README.md", "docs/guide.md", "a/b/c/notes.md"], ["README.mdx", "md", "docs/md/x.txt"],
    "*.md matches .md at any depth (a slash-free pattern matches the basename)")
row("/*.md", ["README.md", "CHANGELOG.md"], ["docs/guide.md", "a/b/c.md"],
    "/*.md matches the top level only")
row("src/components/*.tsx", ["src/components/Button.tsx"],
    ["src/components/ui/Button.tsx", "app/src/components/Button.tsx", "src/Button.tsx"],
    "src/components/*.tsx matches direct children only, not subfolders")

# --- {a,b} expansion and ? ----------------------------------------------------
row("src/**/*.{ts,tsx}", ["src/a.ts", "src/x/b.tsx"], ["src/c.js", "lib/a.ts"],
    "{ts,tsx} expands inside a path pattern")
row("{src,lib}/**/*.rs", ["src/main.rs", "lib/x/y.rs"], ["tests/a.rs"],
    "{src,lib} expands across a leading segment")
row("*.{md,txt}", ["a.md", "docs/b.txt"], ["c.rst"],
    "a slash-free braced pattern still matches at any depth")
row("src/?.rs", ["src/a.rs"], ["src/ab.rs", "src/.rs"], "? matches exactly one character")

# --- unsupported patterns are refused, not emulated ---------------------------
for pat, why in [("src/[ab].rs", "["), ("src/a\\*.rs", "escape"), ("src/{a.rs", "brace"),
                 ("src/a**.rs", "**"), ("docs/", "trailing slash"), ("", "empty")]:
    try:
        sp.glob_match(pat, "src/a.rs")
    except ValueError:
        ok(f"glob_match refuses {pat!r} ({why})")
    else:
        bad(f"glob_match accepted unsupported pattern {pat!r} ({why})")


# --- load_page ----------------------------------------------------------------
GOOD_FM = """---
stack: alpha
paths:
  - "**/*.rs"
  - Cargo.toml
sources: [/home/alice/src/alpha/Cargo.toml, '/home/alice/src/alpha/src/lib.rs']
related:
  - Alpha Crate Layout
checked: 2026-11-17
---
"""


def write(name, text):
    d = os.path.join(WORK, "stacks")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    with open(p, "wb") as f:
        f.write(text.encode("utf-8"))
    return p


def expect_refused(name, text, needle, label):
    p = write(name, text)
    try:
        sp.load_page(p)
    except sp.StackPageError as e:
        msg = str(e)
        if p not in msg:
            bad(f"{label}: refusal does not name the page path: {msg}")
        elif needle.lower() not in msg.lower():
            bad(f"{label}: refusal does not give the reason ({needle!r}): {msg}")
        else:
            ok(f"{label} → refused: {msg.replace(WORK, '$WORK')}")
    except Exception as e:  # noqa: BLE001
        bad(f"{label}: raised {type(e).__name__} instead of StackPageError: {e}")
    else:
        bad(f"{label}: page was accepted")


p = write("alpha.md", GOOD_FM + "# Alpha\n\nUse thiserror.\n")
try:
    page = sp.load_page(p)
except Exception as e:  # noqa: BLE001
    bad(f"good page refused: {e}")
else:
    want = {
        "stack": "alpha",
        "paths": ("**/*.rs", "Cargo.toml"),
        "sources": ("/home/alice/src/alpha/Cargo.toml", "/home/alice/src/alpha/src/lib.rs"),
        "related": ("Alpha Crate Layout",),
        "checked": "2026-11-17",
        "body": "# Alpha\n\nUse thiserror.\n",
    }
    got = {k: (tuple(getattr(page, k)) if isinstance(want[k], tuple) else getattr(page, k))
           for k in want}
    if got != want:
        bad(f"good page parsed wrong:\n  got  {got}\n  want {want}")
    else:
        ok("a good page loads: block list, inline list, quoted and bare strings")

no_related = GOOD_FM.replace("related:\n  - Alpha Crate Layout\n", "")
p = write("alpha.md", no_related + "body\n")
try:
    page = sp.load_page(p)
    if tuple(page.related) != ():
        bad(f"missing related should read as empty, got {page.related!r}")
    else:
        ok("related is optional")
except Exception as e:  # noqa: BLE001
    bad(f"page without related refused: {e}")

expect_refused("alpha.md", GOOD_FM.replace('paths:\n  - "**/*.rs"\n  - Cargo.toml\n', "") + "b\n",
               "paths", "a page with no paths")
expect_refused("alpha.md", GOOD_FM.replace('paths:\n  - "**/*.rs"\n  - Cargo.toml\n', "paths: []\n") + "b\n",
               "paths", "a page with an empty paths list")
expect_refused("alpha.md", GOOD_FM.replace('"**/*.rs"', '"src/[ab].rs"') + "b\n",
               "[", "a pattern holding [")
expect_refused("alpha.md", GOOD_FM.replace("checked:", "owner: alice\nchecked:") + "b\n",
               "owner", "an unknown frontmatter key")
expect_refused("beta.md", GOOD_FM + "b\n", "stem", "stack: differing from the file stem")
expect_refused("Alpha.md", GOOD_FM.replace("stack: alpha", "stack: Alpha") + "b\n",
               "slug", "a slug outside [a-z0-9-]")
expect_refused("alpha.md", GOOD_FM.replace("checked: 2026-11-17\n", "") + "b\n",
               "checked", "a page with no checked date")
expect_refused("alpha.md", GOOD_FM.replace("checked: 2026-11-17", "checked: last week") + "b\n",
               "checked", "a checked value that is not a date")
expect_refused("alpha.md", GOOD_FM.replace("/home/alice/src/alpha/Cargo.toml", "Cargo.toml") + "b\n",
               "absolute", "a relative source path")
expect_refused("alpha.md", GOOD_FM.replace("paths:\n", "paths: {a: b}\n", 1) + "b\n",
               "paths", "a flow-mapping value")
expect_refused("alpha.md", GOOD_FM.replace("stack: alpha", "stack: alpha\nstack: alpha") + "b\n",
               "duplicate", "a duplicate key")
expect_refused("alpha.md", GOOD_FM.replace('  - "**/*.rs"', "  - **/*.rs") + "b\n",
               "quote", "a bare scalar YAML would read as an alias")
expect_refused("alpha.md", GOOD_FM.replace("checked:", "  nested: x\nchecked:") + "b\n",
               "line", "an unparsed frontmatter line")
expect_refused("alpha.md", "stack: alpha\n", "frontmatter", "a page with no frontmatter")
expect_refused("alpha.md", GOOD_FM[:-4] + "b\n", "frontmatter", "a frontmatter with no closing fence")

# --- body size: 8,192 bytes accepted, 8,193 refused ----------------------------
body_ok = ("x" * 8191) + "\n"
assert len(body_ok.encode()) == 8192
p = write("alpha.md", GOOD_FM + body_ok)
try:
    page = sp.load_page(p)
    if page.body != body_ok:
        bad("8,192-byte body was altered on load")
    else:
        ok("a body of 8,192 bytes is accepted whole")
except Exception as e:  # noqa: BLE001
    bad(f"8,192-byte body refused: {e}")
expect_refused("alpha.md", GOOD_FM + "x" + body_ok, "8193", "a body of 8,193 bytes")
# multi-byte text counts bytes, not characters: 4,097 two-byte chars = 8,194 bytes
expect_refused("alpha.md", GOOD_FM + ("é" * 4097), "8194", "a body over the limit in bytes, not characters")

# --- applies ------------------------------------------------------------------
p = write("alpha.md", GOOD_FM + "b\n")
page = sp.load_page(p)
if sp.applies(page, ["README.md", "src/lib.rs"]) is True:
    ok("applies(): true when src/lib.rs is in the file list against **/*.rs")
else:
    bad("applies() false for a list holding src/lib.rs against **/*.rs")
if sp.applies(page, ["README.md"]) is False:
    ok("applies(): false for a list holding only README.md")
else:
    bad("applies() true for a list holding only README.md")
if sp.applies(page, []) is False:
    ok("applies(): false for an empty file list")
else:
    bad("applies() true for an empty file list")


# --- project_files ------------------------------------------------------------
def mk(root, rel):
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "w").close()


plain = os.path.join(WORK, "plain")
for rel in ["src/lib.rs", "README.md", "node_modules/x/index.js", "target/debug/a.rs",
            ".git/config", "build/out.o", "dist/a.js", ".venv/bin/py", "venv/lib/x.py",
            "pkg/__pycache__/m.pyc", ".gradle/c.bin", "pkg/m.py"]:
    mk(plain, rel)
got = sp.project_files(plain)
want = ["README.md", "pkg/m.py", "src/lib.rs"]
if sorted(got) == want:
    ok("project_files outside git: a walk with build and dependency trees pruned")
else:
    bad(f"project_files(plain) = {sorted(got)}, want {want}")

repo = os.path.join(WORK, "repo")
for rel in ["src/lib.rs", "README.md", "scratch.txt"]:
    mk(repo, rel)
env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
subprocess.run(["git", "-C", repo, "init", "-q"], check=True, env=env)
subprocess.run(["git", "-C", repo, "add", "src/lib.rs", "README.md"], check=True, env=env)
got = sp.project_files(repo)
want = ["README.md", "src/lib.rs"]
if sorted(got) == want:
    ok("project_files in a git work tree: git ls-files (untracked file left out)")
else:
    bad(f"project_files(repo) = {sorted(got)}, want {want}")

# --- project_root -------------------------------------------------------------
# A registered project can sit below its git top level (one repo, several project
# folders). The hook, the sidecar and the measure all decide "a stack applies"
# against the same root: the git top level, else the folder itself.
mono = os.path.join(WORK, "mono")
for rel in ["other/src/lib.rs", "sub/notes.txt"]:
    mk(mono, rel)
subprocess.run(["git", "-C", mono, "init", "-q"], check=True, env=env)
subprocess.run(["git", "-C", mono, "add", "-A"], check=True, env=env)
sub = os.path.join(mono, "sub")
got = sp.project_root(sub)
if os.path.realpath(got) == os.path.realpath(mono):
    ok("project_root: a folder inside a git work tree resolves to the git top level")
else:
    bad(f"project_root(mono/sub) = {got}, want {mono}")
got = sp.project_root(plain)
if os.path.realpath(got) == os.path.realpath(plain):
    ok("project_root: a folder outside git is its own root")
else:
    bad(f"project_root(plain) = {got}, want {plain}")
if "other/src/lib.rs" in sp.project_files(sp.project_root(sub)):
    ok("project_files(project_root(sub)) sees a sibling folder's tracked file")
else:
    bad("project_files(project_root(sub)) misses other/src/lib.rs")

sys.exit(1 if failures else 0)
EOF

echo "PASS: test_vault_context_stack_pages.sh"
