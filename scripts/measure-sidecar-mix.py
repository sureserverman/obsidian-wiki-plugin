#!/usr/bin/env python3
"""measure-sidecar-mix.py — measure what vault-context sidecars list, across a registry.

For every registered project that has `<path>/.claude/vault-context.md`, read the
pages the sidecar lists (the `- [[Title]]` bullets under `## <Category>/`
headings between the body markers) and report:

  projects             sidecars measured
  plans_share_median   median share of listed pages that are Plans/ (sidecars
                       listing no page at all are left out of the median)
  no_tech_or_platform  sidecars listing no Technologies/ and no Platforms/ page
  own_project_missing  projects with a Projects/ page in `<vault>/index.md` whose
                       title or file name equals the registry name (without case)
                       while their sidecar does not list that page
  stack_block_missing  projects where a vault stack page applies (lib/stack_pages.py)
                       while the sidecar has no `vault-context:stacks:start` block

--simulate runs the matcher instead of reading the sidecars on disk:
`extract-project-signals.sh | match-index.py <vault>/index.md` from each project's
folder, writing nothing. The stack block is not simulated, so stack_block_missing
is null there and cannot be asserted.

--assert KEY=VALUE (repeatable) bounds a metric; exit 1 when one is beyond its
bound. Keys: plans-median-max, no-tech-max, own-project-missing-max,
stack-block-missing-max.

Prints JSON on stdout. Exit 0 ok; 1 an assertion failed; 2 usage or unreadable input.

This reads the owner's real corpus, so it is a gate command and a task test, never a
file under tests/test_*.sh (CP DEC-022). It never writes a file.
"""

import argparse
import json
import os
import re
import statistics
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "plugins", "vault-context", "scripts")
sys.path.insert(0, os.path.join(SCRIPTS, "lib"))

from stack_pages import StackPageError, applies, load_page, project_files  # noqa: E402

ASSERTS = {
    "plans-median-max": "plans_share_median",
    "no-tech-max": "no_tech_or_platform",
    "own-project-missing-max": "own_project_missing",
    "stack-block-missing-max": "stack_block_missing",
}
RE_CAT = re.compile(r"^##\s+(.+?/)\s*$")
RE_ITEM = re.compile(r"^-\s+\[\[(.+?)\]\]")
BODY_START = "<!-- vault-context:body:start -->"
BODY_END = "<!-- vault-context:body:end -->"
STACKS_START = "<!-- vault-context:stacks:start -->"


def die(msg):
    print(f"measure-sidecar-mix: {msg}", file=sys.stderr)
    sys.exit(2)


def read_registry(path):
    """[(name, path)] from the registry's `- path:` / `name:` entries."""
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as e:
        die(f"cannot read registry {path}: {e.strerror}")
    out, cur = [], None
    for line in text.splitlines():
        mp = re.match(r"\s*-\s*path:\s*(.+?)\s*$", line)
        if mp:
            cur = {"path": os.path.expanduser(mp.group(1).strip("\"'"))}
            out.append(cur)
            continue
        mn = re.match(r"\s+name:\s*(.+?)\s*$", line)
        if mn and cur is not None and "name" not in cur:
            cur["name"] = mn.group(1).strip("\"'")
    return [(e.get("name") or os.path.basename(e["path"].rstrip("/")), e["path"]) for e in out]


def parse_sidecar(text):
    """{category: [titles]} listed in the body, and whether a stack block exists."""
    cats = {}
    body = text
    if BODY_START in text and BODY_END in text:
        body = text.split(BODY_START, 1)[1].split(BODY_END, 1)[0]
    cat = None
    for line in body.splitlines():
        m = RE_CAT.match(line)
        if m:
            cat = m.group(1)
            continue
        m = RE_ITEM.match(line)
        if m and cat:
            cats.setdefault(cat, []).append(m.group(1))
    return cats, STACKS_START in text


def simulate(project, vault):
    """{category: [titles]} the shipped matcher would list for this project."""
    sig = subprocess.run(["bash", os.path.join(SCRIPTS, "extract-project-signals.sh")],
                         cwd=project, capture_output=True, text=True, timeout=120)
    if sig.returncode != 0:
        return None
    m = subprocess.run([sys.executable, os.path.join(SCRIPTS, "match-index.py"),
                        os.path.join(vault, "index.md")],
                       cwd=project, input=sig.stdout, capture_output=True, text=True, timeout=120)
    if m.returncode != 0:
        return None
    if m.stdout.strip().startswith("NO_MATCHES"):
        return {}
    data = json.loads(m.stdout)
    return {c: [p.get("title", "") for p in ps] for c, ps in data.get("matches_by_category", {}).items()}


def load_stacks(vault):
    d = os.path.join(vault, "Portfolio", "stacks")
    pages = []
    if os.path.isdir(d):
        for n in sorted(os.listdir(d)):
            if n.endswith(".md"):
                try:
                    pages.append(load_page(os.path.join(d, n)))
                except StackPageError as e:
                    print(f"measure-sidecar-mix: skipped {e.page}: {e.reason}", file=sys.stderr)
    return pages


def main():
    ap = argparse.ArgumentParser(description="Measure the vault-context sidecar mix.")
    ap.add_argument("--registry", required=True)
    ap.add_argument("--vault", required=True)
    ap.add_argument("--simulate", action="store_true")
    ap.add_argument("--assert", dest="asserts", action="append", default=[], metavar="KEY=VALUE")
    try:
        args = ap.parse_args()
    except SystemExit as e:
        sys.exit(2 if e.code else 0)

    bounds = []
    for a in args.asserts:
        key, sep, val = a.partition("=")
        if not sep or key not in ASSERTS:
            die(f"--assert {a!r}: keys are {', '.join(ASSERTS)}")
        try:
            bounds.append((key, ASSERTS[key], float(val)))
        except ValueError:
            die(f"--assert {a!r}: value is not a number")
    vault = os.path.abspath(os.path.expanduser(args.vault))
    if not os.path.isdir(vault):
        die(f"vault not reachable: {vault}")
    if args.simulate and any(m == "stack_block_missing" for _, m, _ in bounds):
        die("stack-block-missing cannot be asserted under --simulate")

    # Projects/ pages from the index: name (title or file stem, lower) -> titles.
    proj_pages = {}
    idx = os.path.join(vault, "index.md")
    try:
        cat = title = None
        for line in open(idx, encoding="utf-8", errors="replace"):
            m = re.match(r"^##\s+(.+?/)\s*$", line)
            if m:
                cat = m.group(1); title = None
                continue
            m = re.match(r"^###\s+\[\[(.+?)\]\]", line)
            if m:
                title = m.group(1)
                if cat == "Projects/":
                    proj_pages.setdefault(title.lower(), set()).add(title)
                continue
            m = re.match(r"^-\s+path:\s*(.+?)\s*$", line)
            if m and cat == "Projects/" and title:
                stem = os.path.splitext(os.path.basename(m.group(1)))[0].lower()
                proj_pages.setdefault(stem, set()).add(title)
    except OSError:
        pass
    stacks = [] if args.simulate else load_stacks(vault)

    shares, no_tech, own_missing, stack_missing = [], [], [], []
    measured = 0
    for name, path in read_registry(args.registry):
        sidecar = os.path.join(path, ".claude", "vault-context.md")
        if not os.path.isfile(sidecar):
            continue
        try:
            text = open(sidecar, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        cats, has_block = parse_sidecar(text)
        if args.simulate:
            sim = simulate(path, vault)
            if sim is None:
                print(f"measure-sidecar-mix: matcher failed for {name}; left out", file=sys.stderr)
                continue
            cats = sim
        measured += 1
        total = sum(len(v) for v in cats.values())
        if total:
            shares.append(len(cats.get("Plans/", [])) / total)
        if not cats.get("Technologies/") and not cats.get("Platforms/"):
            no_tech.append(name)
        own = proj_pages.get(name.lower())
        if own and not own & set(cats.get("Projects/", [])):
            own_missing.append(name)
        if stacks and not has_block:
            try:
                files = project_files(path)
            except OSError:
                files = []
            if any(applies(p, files) for p in stacks):
                stack_missing.append(name)

    result = {
        "mode": "simulate" if args.simulate else "on-disk",
        "projects": measured,
        "plans_share_median": round(statistics.median(shares), 4) if shares else 0.0,
        "no_tech_or_platform": len(no_tech),
        "own_project_missing": len(own_missing),
        "stack_block_missing": None if args.simulate else len(stack_missing),
        "lists": {
            "no_tech_or_platform": no_tech,
            "own_project_missing": own_missing,
            "stack_block_missing": None if args.simulate else stack_missing,
        },
    }
    print(json.dumps(result, indent=2))

    rc = 0
    for key, metric, bound in bounds:
        val = result[metric]
        if val > bound:
            print(f"measure-sidecar-mix: --assert {key}={bound:g} failed: {metric} is {val}",
                  file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
