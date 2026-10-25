#!/usr/bin/env python3
"""check-vendor.py — vault-portfolio's vendored copy of the planning lib matches its lock.

    check-vendor.py --upstream <planning repo>            check
    check-vendor.py --upstream <planning repo> --write    re-vendor every locked file

vault-portfolio reads plans with the planning plugin's own parser, copied into
src/vault-portfolio/core/vendor/staged_planning/ so the plugin never imports from
another plugin's install. A copy drifts silently, so vendor.lock pins each file:

    <file> <sha256> <upstream commit>

The check fails (exit 1) when a vendored file differs from its lock hash, when the
upstream repo's core/lib/<file> differs from it (in the working tree or at HEAD),
when the lock's commit does not hold those bytes, or when the vendored package
holds a file the lock does not name. It reads the checkout it is given and fetches
nothing: a checkout that is behind its own remote is compared as it stands.
`--write` copies every locked file from the upstream checkout and rewrites the
lock with the upstream HEAD; it refuses a file with uncommitted upstream changes,
because HEAD would then not be where the copied bytes came from.

Exit codes: 0 match · 1 drift · 2 usage error or a lock line this tool cannot
parse (it never guesses at one).
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "src" / "vault-portfolio" / "core" / "vendor"
PACKAGE = VENDOR / "staged_planning"
LOCK = VENDOR / "vendor.lock"
UPSTREAM_LIB = "core/lib"

LINE_RE = re.compile(r"^([A-Za-z0-9_.-]+\.py) ([0-9a-f]{64}) ([0-9a-f]{40})$")


class Usage(Exception):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(upstream: Path, *args: str, binary: bool = False):
    out = subprocess.run(["git", "-C", str(upstream), *args], capture_output=True)
    if out.returncode != 0:
        return None
    return out.stdout if binary else out.stdout.decode().strip()


def read_lock() -> list[tuple[str, str, str]]:
    if not LOCK.is_file():
        raise Usage(f"no lock at {LOCK.relative_to(ROOT)}")
    entries = []
    for n, line in enumerate(LOCK.read_text().splitlines(), 1):
        if not line.strip():
            continue
        m = LINE_RE.match(line)
        if not m:
            raise Usage(f"vendor.lock:{n}: not '<file> <sha256> <commit>': {line!r}")
        entries.append(m.groups())
    if not entries:
        raise Usage("vendor.lock names no file")
    return entries


def check(upstream: Path) -> list[str]:
    entries = read_lock()
    if not git(upstream, "rev-parse", "HEAD"):
        raise Usage(f"{upstream} is not a git repository with a commit")
    problems = []
    for name, locked, commit in entries:
        vendored = PACKAGE / name
        if not vendored.is_file():
            problems.append(f"{name}: no vendored copy")
        elif sha256(vendored.read_bytes()) != locked:
            problems.append(f"{name}: the vendored copy differs from its lock")
        current = upstream / UPSTREAM_LIB / name
        if not current.is_file():
            problems.append(f"{name}: upstream has no {UPSTREAM_LIB}/{name}")
        elif sha256(current.read_bytes()) != locked:
            problems.append(f"{name}: upstream {UPSTREAM_LIB}/{name} differs from the lock "
                            "(re-vendor with --write)")
        at_head = git(upstream, "show", f"HEAD:{UPSTREAM_LIB}/{name}", binary=True)
        if at_head is not None and sha256(at_head) != locked:
            problems.append(f"{name}: upstream HEAD's {UPSTREAM_LIB}/{name} differs from the lock "
                            "(re-vendor with --write)")
        at_commit = git(upstream, "show", f"{commit}:{UPSTREAM_LIB}/{name}", binary=True)
        if at_commit is None:
            problems.append(f"{name}: lock commit {commit[:12]} has no {UPSTREAM_LIB}/{name}")
        elif sha256(at_commit) != locked:
            problems.append(f"{name}: lock commit {commit[:12]} does not hold the locked bytes")
    named = {name for name, _, _ in entries}
    for path in sorted(PACKAGE.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts \
                and path.relative_to(PACKAGE).as_posix() not in named:
            problems.append(f"{path.relative_to(PACKAGE).as_posix()}: vendored but not locked")
    return problems


def write(upstream: Path) -> None:
    names = [name for name, _, _ in read_lock()]
    head = git(upstream, "rev-parse", "HEAD")
    if not head:
        raise Usage(f"{upstream} is not a git repository with a commit")
    for name in names:
        rel = f"{UPSTREAM_LIB}/{name}"
        if git(upstream, "status", "--porcelain", "--", rel):
            raise Usage(f"upstream {rel} has uncommitted changes; commit them first")
        if not (upstream / rel).is_file():
            raise Usage(f"upstream has no {rel}")
    PACKAGE.mkdir(parents=True, exist_ok=True)
    lines = []
    for name in names:
        src = upstream / UPSTREAM_LIB / name
        shutil.copyfile(src, PACKAGE / name)
        lines.append(f"{name} {sha256(src.read_bytes())} {head}")
    LOCK.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--upstream", required=True, type=Path,
                    help="the planning repo checkout the lib is vendored from")
    ap.add_argument("--write", action="store_true",
                    help="re-copy every locked file from upstream and rewrite the lock")
    args = ap.parse_args()
    upstream = args.upstream.resolve()
    try:
        if args.write:
            write(upstream)
            print(f"check-vendor: re-vendored from {git(upstream, 'rev-parse', '--short', 'HEAD')}")
            return 0
        problems = check(upstream)
    except Usage as e:
        print(f"check-vendor: {e}", file=sys.stderr)
        return 2
    for p in problems:
        print(f"check-vendor: {p}", file=sys.stderr)
    if problems:
        return 1
    print("check-vendor: vendored files match the lock and upstream")
    return 0


if __name__ == "__main__":
    sys.exit(main())
