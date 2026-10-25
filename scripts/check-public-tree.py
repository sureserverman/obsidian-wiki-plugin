#!/usr/bin/env python3
"""check-public-tree.py — fail when a tracked file names a real home or mount path.

The repository is public, so no tracked file may point at a maintainer's machine: an
absolute home path (/home/<name>/, /Users/<name>/), a private mount (/mnt/<name>/), or a
home path as Claude Code and Cursor encode it in a project folder name (-home-<name>-…).
Documentation uses placeholders instead, listed in PLACEHOLDERS. The check needs no
private data, so CI can run it on every push.

Exit 0: clean. Exit 1: findings, one `path:line: match` per line. Exit 2: a tracked file
could not be read, or --root is not a git work tree (DEC-002: refuse, never pass).
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

PLACEHOLDERS = {"alice", "bob", "someone", "x", "you", "example", "notes"}
PATH_RE = re.compile(r"/(?:home|Users|mnt)/([A-Za-z0-9._-]+)")
# The same home folder as Claude Code and Cursor encode it in a project folder name:
# /home/<name>/dev/x becomes -home-<name>-dev-x (Claude) or home-<name>-dev-x (Cursor).
ENCODED_RE = re.compile(r"(?<![A-Za-z0-9])-?home-([A-Za-z0-9._]+)-")


def tracked(root):
    """Tracked regular files. A symlink (120000) or submodule (160000) holds no text to read."""
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-s", "-z"], capture_output=True)
    if out.returncode != 0:
        raise OSError(f"not a git work tree: {root}")
    entries = (e.split("\t", 1) for e in out.stdout.decode().split("\0") if e)
    return [path for meta, path in entries if meta.split()[0] not in ("120000", "160000")]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=Path(__file__).resolve().parent.parent, type=Path)
    root = ap.parse_args().root
    findings = []
    try:
        for rel in tracked(root):
            data = (root / rel).read_bytes()
            if b"\0" in data:
                continue
            for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
                for m in (*PATH_RE.finditer(line), *ENCODED_RE.finditer(line)):
                    if m.group(1) not in PLACEHOLDERS:
                        findings.append(f"{rel}:{n}: {m.group(0)}")
    except OSError as e:
        print(f"check-public-tree: {e}", file=sys.stderr)
        return 2
    for f in findings:
        print(f)
    print(f"check-public-tree: {len(findings)} finding(s)", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
