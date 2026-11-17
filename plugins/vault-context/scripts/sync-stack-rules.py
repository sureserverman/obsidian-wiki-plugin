#!/usr/bin/env python3
"""sync-stack-rules.py — turn the vault's stack pages into Claude Code rules.

Each `<vault>/Portfolio/stacks/<slug>.md` becomes `vault-stack-<slug>.md` in the
rules folder: frontmatter holding only `paths`, then a marker line, then the
page body byte for byte. Claude Code loads the rule when a matching file is
read, written or edited.

The marker is an HTML comment, so a renderer shows nothing for it (Claude Code
documents stripping block-level comments for CLAUDE.md files):

    <!-- vault-context:stack-rule source=<slug> sha256=<sha256 of the page file> -->

The tool changes or removes only files that carry it. A `vault-stack-*.md`
without it stops the run, named and untouched. Every other file in the rules
folder is never read.

Modes:
  (default)   write, update and remove rules; print how many
  --check     compare only; exit 1 on any drift (missing, stale, orphan rule),
              a refused page or a foreign file
  --lint      validate pages only, including that every `sources` path exists
  --json      print the result as JSON

Exit: 0 in sync; 1 drift, lint error or refusal; 2 usage, vault not reachable,
or a file-system error (an unreadable rule, an unwritable rules folder).
A missing vault never deletes a rule, and neither does a vault that shows no
stack pages at all (a half-mounted or wrong vault looks exactly like that): a
write run that would remove every rule it finds stops with exit 2 instead.

A foreign `vault-stack-*.md` fails every mode, `--only` and `--lint` included:
it would shadow or be mistaken for a generated rule whichever page is synced.

Folders:
  vault  --vault, else resolve-vault.sh
  rules  --rules-dir, else $VAULT_CONTEXT_RULES_DIR, else
         ${CLAUDE_CONFIG_DIR:-~/.claude}/rules

vault-context never writes to the vault (W DEC-003); a page it cannot parse is
refused, never guessed at (W DEC-002).
"""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))

from stack_pages import StackPageError, load_page  # noqa: E402

RULE_PREFIX = "vault-stack-"
RULE_SUFFIX = ".md"
MARKER_RE = re.compile(
    r"^<!-- vault-context:stack-rule source=([a-z0-9-]+) sha256=([0-9a-f]{64}) -->$"
)
HOSTS = ("claude",)


def die(msg, code=2):
    print(f"sync-stack-rules: {msg}", file=sys.stderr)
    sys.exit(code)


def resolve_vault(arg):
    if arg:
        return os.path.abspath(os.path.expanduser(arg))
    try:
        out = subprocess.run(
            ["bash", os.path.join(HERE, "resolve-vault.sh")],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        die(f"vault not reachable: resolve-vault.sh failed ({e})")
    if out.returncode != 0 or not out.stdout.strip():
        die("vault not reachable: resolve-vault.sh found no vault "
            f"({out.stderr.strip() or 'no output'})")
    return out.stdout.strip()


def resolve_rules_dir(arg):
    if arg:
        return os.path.abspath(os.path.expanduser(arg))
    env = os.environ.get("VAULT_CONTEXT_RULES_DIR")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    cfg = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(cfg, "rules")


def rule_text(page, page_sha):
    """The exact bytes a page's rule holds."""
    marker = f"<!-- vault-context:stack-rule source={page.stack} sha256={page_sha} -->"
    paths = json.dumps(list(page.paths), ensure_ascii=False)
    return f"---\npaths: {paths}\n---\n{marker}\n{page.body}".encode("utf-8")


def read_marker(path):
    """(slug, sha) from a generated rule, or None when the file is not ours.

    A symlink, a non-regular file, or a file without the marker directly after
    its frontmatter is not ours.
    """
    try:
        st = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    try:
        with open(path, "rb") as f:
            text = f.read(1 << 20).decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        return None
    try:
        close = lines.index("---", 1)
    except ValueError:
        return None
    if close + 1 >= len(lines):
        return None
    m = MARKER_RE.match(lines[close + 1])
    return (m.group(1), m.group(2)) if m else None


def scan_rules(rules_dir):
    """Generated rules by slug, and foreign vault-stack-* files."""
    ours, foreign = {}, []
    if not os.path.isdir(rules_dir):
        return ours, foreign
    for name in sorted(os.listdir(rules_dir)):
        if not (name.startswith(RULE_PREFIX) and name.endswith(RULE_SUFFIX)):
            continue
        path = os.path.join(rules_dir, name)
        slug = name[len(RULE_PREFIX):-len(RULE_SUFFIX)]
        mk = read_marker(path)
        if mk is None or mk[0] != slug:
            foreign.append(path)
        else:
            ours[slug] = path
    return ours, foreign


def write_atomic(path, data):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".vault-stack-", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate Claude Code rules from vault stack pages.")
    ap.add_argument("--vault")
    ap.add_argument("--rules-dir")
    ap.add_argument("--host", default="claude")
    ap.add_argument("--only", metavar="SLUG")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--lint", action="store_true")
    ap.add_argument("--json", action="store_true")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        sys.exit(2 if e.code else 0)

    if args.host not in HOSTS:
        die(f"--host {args.host} is not supported (supported: {', '.join(HOSTS)})")
    if args.only is not None and not re.fullmatch(r"[a-z0-9-]+", args.only):
        die(f"--only {args.only!r} is not a slug ([a-z0-9-]+)")

    vault = resolve_vault(args.vault)
    if not os.path.isdir(vault):
        die(f"vault not reachable: {vault}")
    rules_dir = resolve_rules_dir(args.rules_dir)
    stacks_dir = os.path.join(vault, "Portfolio", "stacks")
    write_mode = not (args.check or args.lint)

    # --- pages -------------------------------------------------------------
    page_files = []
    if os.path.isdir(stacks_dir):
        page_files = sorted(
            n for n in os.listdir(stacks_dir)
            if n.endswith(".md") and os.path.isfile(os.path.join(stacks_dir, n))
        )
    present = {n[:-3] for n in page_files}
    if args.only is not None:
        page_files = [n for n in page_files if n[:-3] == args.only]

    pages, errors, sources_missing = [], [], []
    for name in page_files:
        path = os.path.join(stacks_dir, name)
        try:
            page = load_page(path)
        except StackPageError as e:
            errors.append({"page": path, "slug": name[:-3], "reason": e.reason})
            continue
        with open(path, "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()
        pages.append((page, sha))
        for src in page.sources:
            if not os.path.exists(src):
                sources_missing.append({"slug": page.stack, "path": src})

    # --- rules -------------------------------------------------------------
    ours, foreign = scan_rules(rules_dir)
    if args.only is not None:
        ours = {s: p for s, p in ours.items() if s == args.only}
    orphans = [{"slug": s, "rule": p} for s, p in sorted(ours.items()) if s not in present]

    states = []
    for page, sha in pages:
        rule = os.path.join(rules_dir, f"{RULE_PREFIX}{page.stack}{RULE_SUFFIX}")
        want = rule_text(page, sha)
        if page.stack not in ours:
            state = "missing"
        else:
            with open(rule, "rb") as f:
                state = "in-sync" if f.read() == want else "stale"
        states.append({"slug": page.stack, "state": state, "rule": rule, "_want": want})

    result = {
        "vault": vault,
        "rules_dir": rules_dir,
        "pages": [{k: v for k, v in s.items() if k != "_want"} for s in states],
        "orphans": orphans,
        "foreign": foreign,
        "errors": errors,
        "sources_missing": sources_missing,
    }

    counts = {"wrote": 0, "updated": 0, "removed": 0, "unchanged": 0}
    rc = 0
    if write_mode:
        if foreign:
            rc = 1  # refuse the whole run: nothing is written or removed
        elif orphans and not present:
            # No page at all, yet generated rules exist: a missing, empty or
            # half-mounted stacks folder. Removing every rule on that evidence
            # is the one mistake this tool must not make.
            if not args.json:
                print(f"sync-stack-rules: no stack pages in {stacks_dir}, yet "
                      f"{len(orphans)} generated rule(s) exist; removing none. If every page "
                      "was deleted on purpose, remove the vault-stack-*.md files by hand",
                      file=sys.stderr)
            rc = 2
        else:
            pending = [s for s in states if s["state"] != "in-sync"]
            if pending:
                os.makedirs(rules_dir, exist_ok=True)
            for s in states:
                if s["state"] == "in-sync":
                    counts["unchanged"] += 1
                    continue
                write_atomic(s["rule"], s["_want"])
                counts["wrote" if s["state"] == "missing" else "updated"] += 1
                s["action"] = "wrote" if s["state"] == "missing" else "updated"
                s["state"] = "in-sync"
            for o in orphans:
                # Re-check the marker right before deleting. A writer racing this
                # in the user's own config folder is outside what this guards.
                mk = read_marker(o["rule"])
                if mk and mk[0] == o["slug"]:
                    os.unlink(o["rule"])
                    counts["removed"] += 1
            if errors:
                rc = 1
        result["counts"] = counts
        result["pages"] = [{k: v for k, v in s.items() if k != "_want"} for s in states]
    else:
        drift = any(s["state"] != "in-sync" for s in states) or orphans
        if args.check and drift:
            rc = 1
        if foreign or errors:
            rc = 1
        if args.lint and sources_missing:
            rc = 1

    # --- report ------------------------------------------------------------
    if args.json:
        print(json.dumps(result, indent=2))
        return rc

    for f in foreign:
        print(f"sync-stack-rules: refusing: {f} is named like a generated rule "
              "but has no vault-context marker; it was not touched", file=sys.stderr)
    for e in errors:
        print(f"sync-stack-rules: page refused: {e['page']}: {e['reason']}", file=sys.stderr)
    for m in sources_missing:
        lvl = "lint error" if args.lint else "warning"
        print(f"sync-stack-rules: {lvl}: {m['slug']}: sources path does not exist: {m['path']}",
              file=sys.stderr)
    if write_mode:
        if foreign:
            print("sync-stack-rules: nothing written", file=sys.stderr)
        elif rc != 2:
            print(f"stack rules in {rules_dir}: wrote {counts['wrote']}, "
                  f"updated {counts['updated']}, removed {counts['removed']}, "
                  f"unchanged {counts['unchanged']}")
    elif args.check:
        for s in states:
            if s["state"] != "in-sync":
                print(f"{s['state']}: {s['slug']} ({s['rule']})")
        for o in orphans:
            print(f"orphan: {o['slug']} ({o['rule']}) — its page is gone")
        if rc == 0:
            print(f"stack rules in sync: {len(states)} page(s)")
    elif rc == 0:
        print(f"stack pages lint clean: {len(pages)} page(s)")
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except OSError as e:
        die(f"file-system error: {e.filename or ''}: {e.strerror or e}")
