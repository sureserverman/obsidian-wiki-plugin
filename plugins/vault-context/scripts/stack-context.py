#!/usr/bin/env python3
"""stack-context.py — SessionStart hook: add the stack pages that apply to this project.

Claude Code runs it at session start, resume, /clear and compaction with the hook
input as JSON on stdin. It takes the project root as the git top level of the
input's `cwd` (else `cwd` itself), lists the project's files, and for each copy
`/vault-context:sync-rules` wrote to the stacks folder, in slug order, asks
whether the copy's `paths` match one of them (lib/stack_pages.py: `project_files`,
`applies`). It prints one JSON object

    {"hookSpecificOutput": {"hookEventName": "SessionStart",
                            "additionalContext": "<each applying copy, whole>"}}

holding each applying copy whole, marker line included, while the total stays at
most BUDGET characters (Claude Code caps one hook's context at 10,000). A copy
that does not fit is named in one line with its path, to read. No applying copy
→ no output.

Stacks folder: $VAULT_CONTEXT_STACKS_DIR, else ${CLAUDE_CONFIG_DIR:-~/.claude}/vault-stacks
(the same resolution as sync-stack-rules.py). Only files carrying the
`vault-context:stack-rule source=<slug>` marker for their own slug count.

It reads only local files, never the vault, and writes nothing (no bytecode
either). On any error, or when listing the project takes longer than
TIME_LIMIT seconds, it prints nothing and exits 0, so a broken hook never blocks
a session.
"""

import sys

sys.dont_write_bytecode = True

import importlib.util  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import signal  # noqa: E402
import subprocess  # noqa: E402

BUDGET = 9500
TIME_LIMIT = 10

HERE = os.path.dirname(os.path.abspath(__file__))


class _TimeUp(Exception):
    pass


def _load_sync():
    """sync-stack-rules.py as a module: one definition of the folder and marker."""
    spec = importlib.util.spec_from_file_location(
        "vault_context_sync_stack_rules", os.path.join(HERE, "sync-stack-rules.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _project_root(cwd):
    try:
        out = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return cwd
    top = out.stdout.strip()
    return top if out.returncode == 0 and top and os.path.isdir(top) else cwd


def _copy_paths(text):
    """The `paths` list from a copy's frontmatter (`paths: [json list]`), or None."""
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        return None
    for line in lines[1:]:
        if line == "---":
            return None
        if line.startswith("paths: "):
            try:
                paths = json.loads(line[len("paths: "):])
            except ValueError:
                return None
            if isinstance(paths, list) and paths and all(isinstance(p, str) for p in paths):
                return paths
            return None
    return None


def _chars(s):
    # Count UTF-16 code units, as Claude Code's JavaScript string length does; for
    # text outside the BMP this is more than len(), so the budget stays safe.
    return len(s.encode("utf-16-le")) // 2


def build_context(cwd):
    sync = _load_sync()
    from stack_pages import StackPage, applies, project_files  # sync put lib/ on sys.path

    stacks = sync.resolve_stacks_dir()
    if not os.path.isdir(stacks):
        return None
    copies = []
    for name in sorted(os.listdir(stacks)):
        if not (name.startswith(sync.RULE_PREFIX) and name.endswith(sync.RULE_SUFFIX)):
            continue
        slug = name[len(sync.RULE_PREFIX):-len(sync.RULE_SUFFIX)]
        path = os.path.join(stacks, name)
        try:
            mk = sync.read_marker(path)
            if mk is None or mk[0] != slug:
                continue
            with open(path, "rb") as f:
                text = f.read().decode("utf-8")
        except (OSError, UnicodeDecodeError, ValueError):
            continue  # one unreadable copy must not silence the others
        paths = _copy_paths(text)
        if paths is None:
            continue
        copies.append((slug, path, paths, text))
    if not copies:
        return None

    files = project_files(_project_root(cwd))
    parts, used = [], 0
    for slug, path, paths, text in copies:
        page = StackPage(path=path, stack=slug, paths=tuple(paths), sources=(),
                         related=(), checked="", body="")
        try:
            hit = applies(page, files)
        except ValueError:
            continue  # a glob outside the supported subset: the sync refuses such pages
        if not hit:
            continue
        sep = 1 if parts else 0
        if used + sep + _chars(text) <= BUDGET:
            parts.append(text)
            used += sep + _chars(text)
            continue
        note = (f"[vault-context] The {slug} stack page applies to this project but did not "
                f"fit in the session-start context; read {path}")
        if used + sep + _chars(note) <= BUDGET:
            parts.append(note)
            used += sep + _chars(note)
    return "\n".join(parts) if parts else None


def main():
    data = json.loads(sys.stdin.read() or "{}")
    if not isinstance(data, dict):
        return
    cwd = data.get("cwd") or os.getcwd()
    if not isinstance(cwd, str) or not os.path.isdir(cwd):
        return
    if hasattr(signal, "SIGALRM"):
        def _up(signum, frame):
            raise _TimeUp()
        signal.signal(signal.SIGALRM, _up)
        signal.alarm(TIME_LIMIT)
    ctx = build_context(os.path.abspath(cwd))
    if hasattr(signal, "SIGALRM"):
        signal.alarm(0)
    if ctx:
        out = {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                      "additionalContext": ctx}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    try:
        main()
    except BaseException:  # noqa: BLE001 — a broken hook must never block a session
        pass
    sys.exit(0)
