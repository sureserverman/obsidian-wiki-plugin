#!/usr/bin/env python3
"""check-moved-set.py — every member of the planning repo's old portfolio layer went somewhere.

    check-moved-set.py --source-repo <planning repo> --source-rev <rev> [--complete [--only RE]]

vault-portfolio was cut out of the planning repo. The set that left is every file
under core/skills/{portfolio,compass,decisions} at <rev>, and each member must be
accounted for exactly once, in one of two files under src/vault-portfolio/:

  moved-from.txt   <W path> <- <source path>            the file now lives here
  not-moved.txt    <source path> -> R:<path>            kept in the planning repo
                   <source path> -> replaced:<W dir>     real fixtures replaced by synthetic ones
                   <source path> -> dropped: <reason>

A not-moved.txt source path ending in `/` is a prefix and claims every member
under it. Blank lines and lines starting with `#` are skipped; any other line
that does not parse is refused (exit 2), never guessed at.

The check fails (exit 1) when a source path is not a member at <rev>, when an R:
target is not in the source repo's HEAD, when a member is claimed twice, when two
moved lines share a destination, or when a member is claimed by no line. A W path
this repo does not track yet is printed as `pending`; it fails only under
--complete, which also needs every replaced: dir to hold a tracked file. --only
limits that completeness demand to the lines whose W path matches the regular
expression.

Exit codes: 0 accounted for · 1 a member unaccounted for or a claim that does not
hold · 2 usage error or an unparseable line.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VP = ROOT / "src" / "vault-portfolio"
MOVED = VP / "moved-from.txt"
NOT_MOVED = VP / "not-moved.txt"
SET_DIRS = ["core/skills/portfolio", "core/skills/compass", "core/skills/decisions"]

PATH = r"[A-Za-z0-9._/-]+"
MOVED_RE = re.compile(rf"^({PATH}) <- ({PATH})$")
NOT_MOVED_RE = re.compile(rf"^({PATH}) -> (?:R:({PATH})|replaced:({PATH})|dropped: (\S.*))$")


class Usage(Exception):
    pass


def lines(path: Path):
    if not path.is_file():
        raise Usage(f"no {path.relative_to(ROOT)}")
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if line.strip() and not line.lstrip().startswith("#"):
            yield n, line


def read_claims():
    """[(source path, kind, W path or R path or reason, where)] from both files."""
    claims = []
    for n, line in lines(MOVED):
        m = MOVED_RE.match(line)
        if not m:
            raise Usage(f"moved-from.txt:{n}: not '<W path> <- <source path>': {line!r}")
        claims.append((m.group(2), "moved", m.group(1), f"moved-from.txt:{n}"))
    for n, line in lines(NOT_MOVED):
        m = NOT_MOVED_RE.match(line)
        if not m:
            raise Usage(f"not-moved.txt:{n}: not '<source path> -> R:|replaced:|dropped: …': "
                        f"{line!r}")
        src, kept, replaced, reason = m.groups()
        if kept:
            claims.append((src, "R", kept, f"not-moved.txt:{n}"))
        elif replaced:
            claims.append((src, "replaced", replaced, f"not-moved.txt:{n}"))
        else:
            claims.append((src, "dropped", reason, f"not-moved.txt:{n}"))
    return claims


def members(repo: Path, rev: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "-z", "--name-only", rev,
                          *SET_DIRS], capture_output=True, text=True)
    if out.returncode != 0:
        raise Usage(f"cannot list {rev} in {repo}: {out.stderr.strip()}")
    found = [p for p in out.stdout.split("\0") if p]
    if not found:
        raise Usage(f"{rev} has no member under {', '.join(SET_DIRS)}")
    return found


def tracked() -> set[str]:
    """Paths this repo's index holds: a destination counts as present only when tracked."""
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, text=True)
    if out.returncode != 0:
        raise Usage(f"{ROOT} is not a git work tree: {out.stderr.strip()}")
    return {p for p in out.stdout.split("\0") if p}


def committed(repo: Path, path: str) -> bool:
    """True when the source repo's HEAD holds <path> (a file or a directory)."""
    return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"HEAD:{path}"],
                          capture_output=True).returncode == 0


def covers(src: str, member: str) -> bool:
    return member.startswith(src) if src.endswith("/") else member == src


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source-repo", required=True, type=Path)
    ap.add_argument("--source-rev", required=True)
    ap.add_argument("--complete", action="store_true",
                    help="every claimed W path must exist, and every replaced: dir be non-empty")
    ap.add_argument("--only", metavar="RE",
                    help="with --complete, demand completeness only of W paths matching RE")
    args = ap.parse_args()
    try:
        only = re.compile(args.only) if args.only else None
        claims = read_claims()
        member_list = members(args.source_repo, args.source_rev)
        present = tracked()
    except (Usage, re.error) as e:
        print(f"check-moved-set: {e}", file=sys.stderr)
        return 2

    problems, pending = [], []
    claimed_by = {m: [] for m in member_list}
    for src, kind, target, where in claims:
        hit = [m for m in member_list if covers(src, m)]
        if not hit:
            problems.append(f"{where}: {src} is not a member at {args.source_rev}")
        for m in hit:
            claimed_by[m].append(where)
        if kind == "R" and not committed(args.source_repo, target):
            problems.append(f"{where}: R:{target} is not in the source repo's HEAD")
        if kind in ("moved", "replaced"):
            done = target in present if kind == "moved" else any(
                p.startswith(target.rstrip("/") + "/") for p in present)
            if not done:
                pending.append((target, where))
    destinations = {}
    for _src, kind, target, where in claims:
        if kind == "moved":
            destinations.setdefault(target, []).append(where)
    for target, where in destinations.items():
        if len(where) > 1:
            problems.append(f"{target}: the destination of {len(where)} lines ({', '.join(where)})")
    for m, where in claimed_by.items():
        if not where:
            problems.append(f"{m}: claimed by no line")
        elif len(where) > 1:
            problems.append(f"{m}: claimed {len(where)} times ({', '.join(where)})")

    for target, where in pending:  # not yet tracked in this repo
        demanded = args.complete and (only is None or only.search(target))
        print(f"{'missing' if demanded else 'pending'} {target} ({where})")
        if demanded:
            problems.append(f"{where}: {target} does not exist yet")
    for p in problems:
        print(f"check-moved-set: {p}", file=sys.stderr)
    if problems:
        return 1
    print(f"check-moved-set: {len(member_list)} members accounted for, {len(pending)} pending")
    return 0


if __name__ == "__main__":
    sys.exit(main())
