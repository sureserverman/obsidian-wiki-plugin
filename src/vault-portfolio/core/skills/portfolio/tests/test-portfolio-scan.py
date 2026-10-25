#!/usr/bin/env python3
"""portfolio-scan: the walk, the drift report, and the single-entry registry edits.

Pins:
  * the walk finds docs/plans/, docs/backlog.md and .claude/vault-context.md roots,
    and not a bare docs/ or a symlinked directory;
  * a found root that fails the containment rule (not a git repo, not registered)
    is listed as not addable, and --add of it is refused (exit 1, no write);
  * first run: no registry and no --root is exit 2; --add-all without --write
    creates nothing; with --write it creates the registry;
  * later runs derive the roots from the registry and report drift both ways;
  * --remove takes out exactly one entry and keeps every other byte, including a
    comment or blank run that sits before the next entry; a dry run of a removal
    that would be refused reports the refusal;
  * --write needs a reachable vault;
  * area and name are records-home's derivation (parent folder, last folder, as
    written), so scan registers what records-home resolves;
  * a projects root derived from the registry that is /, $HOME or shallower than
    three folders is refused with "pass --root";
  * --json with an edit flag is a usage error, and a malformed legacy config is
    exit 2.

Throwaway HOME, vault and projects root only. Stdlib + PyYAML, no pytest. Run:
  python3 -I src/vault-portfolio/core/skills/portfolio/tests/test-portfolio-scan.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "portfolio-scan.py"
RECORDS_HOME = HERE.parents[2] / "scripts" / "records-home.py"

failures: list[str] = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        failures.append(name)
        print(f"FAIL  {name}  {detail}")


T = Path(tempfile.mkdtemp(prefix="scan-test-")).resolve()
HOME = T / "home"
VAULT = T / "vault"
DEV = T / "dev"
REG = T / "registry.yaml"
CONFIG = HOME / ".config" / "obsidian-wiki" / "config.json"


def env():
    return {"HOME": str(HOME), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}


def config(vault):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({"default_vault": str(vault), "registry": str(REG)}))


def run(*args, script=SCRIPT):
    r = subprocess.run([sys.executable, "-I", str(script), *map(str, args)], env=env(),
                       capture_output=True, text=True, timeout=60, cwd="/")
    return r.returncode, r.stdout, r.stderr


def clean(err):
    return "Traceback" not in err


def project(rel, *markers, git=True):
    p = DEV / rel
    p.mkdir(parents=True, exist_ok=True)
    if git:
        (p / ".git").mkdir(exist_ok=True)
    for m in markers:
        target = p / m
        if m.endswith(".md"):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x\n")
        else:
            target.mkdir(parents=True, exist_ok=True)
    return p


try:
    (VAULT / "Portfolio").mkdir(parents=True)
    config(VAULT)
    alpha = project("apps/alpha", "docs/plans")
    beta = project("apps/beta", "docs/backlog.md")
    gamma = project("tools/gamma", ".claude/vault-context.md")
    project("apps/bare", "docs")
    nogit = project("apps/nogit", "docs/plans", git=False)
    elsewhere = T / "elsewhere"
    (elsewhere / "docs" / "plans").mkdir(parents=True)
    (DEV / "apps" / "linked").symlink_to(elsewhere, target_is_directory=True)

    print("first run:")
    rc, out, err = run()
    check("no registry and no --root is exit 2", rc == 2, f"rc={rc} {err}")
    check("it says to pass --root", "--root" in err, err)

    rc, out, err = run("--root", str(DEV), "--json")
    doc = json.loads(out) if rc == 0 else {}
    found = {c["path"]: c for c in doc.get("found_not_in_registry", [])}
    check("the walk finds the three marker kinds and the non-git root",
          set(found) == {str(alpha), str(beta), str(gamma), str(nogit)}, sorted(found))
    check("area and name come from the path",
          found.get(str(gamma), {}).get("area") == "tools"
          and found.get(str(gamma), {}).get("name") == "gamma", found.get(str(gamma)))
    check("the non-git, unregistered root is not addable",
          found.get(str(nogit), {}).get("addable") is False, found.get(str(nogit)))
    check("the git roots are addable",
          all(found.get(str(p), {}).get("addable") for p in (alpha, beta, gamma)))
    check("the dry run creates no registry", not REG.exists())

    rc, out, err = run("--root", str(DEV), "--add-all")
    check("--add-all without --write only says what it would do",
          rc == 0 and "would add" in out and not REG.exists(), f"rc={rc} {out}{err}")

    rc, out, err = run("--root", str(DEV), "--add", str(nogit), "--write")
    check("--add of a not-addable root is refused with exit 1, naming the root and the "
          "containment rule",
          rc == 1 and f"REFUSED --add {nogit}: not addable — " in out
          and "area directory" in out and clean(err), f"rc={rc} {out}{err}")
    check("the refused add writes no registry", not REG.exists())

    rc, out, err = run("--root", str(DEV), "--add-all", "--write")
    check("--add-all --write exits 0", rc == 0, f"rc={rc} {out}{err}")
    data = yaml.safe_load(REG.read_text()) if REG.exists() else {}
    paths = [p["path"] for p in data.get("projects", [])]
    check("the registry is created with the three addable roots",
          sorted(paths) == sorted(map(str, (alpha, beta, gamma))), paths)
    check("each entry is enabled and dated",
          all(p.get("enabled") is True and p.get("added") for p in data.get("projects", [])))

    print("later runs:")
    rc, out, err = run()
    check("the roots come from the registry", rc == 0 and f"projects roots: {DEV}" in out,
          f"rc={rc} {out}{err}")
    check("the drift header prints", "Drift — found not in registry: 1 | "
          "registered but missing on disk: 0" in out, out)

    shutil.rmtree(gamma)
    before = REG.read_text()
    rc, out, err = run("--json")
    doc = json.loads(out) if rc == 0 else {}
    check("a removed project shows as missing on disk",
          [m["path"] for m in doc.get("registered_but_missing_on_disk", [])] == [str(gamma)],
          doc.get("registered_but_missing_on_disk"))
    rc, out, err = run("--root", str(DEV), "--remove", str(gamma))
    check("--remove without --write writes nothing",
          rc == 0 and "would remove" in out and REG.read_text() == before, out)
    rc, out, err = run("--root", str(DEV), "--remove", str(gamma), "--write")
    after = REG.read_text()
    check("--remove --write exits 0", rc == 0, f"rc={rc} {out}{err}")
    left = [p["path"] for p in yaml.safe_load(after)["projects"]]
    check("exactly that entry is gone", sorted(left) == sorted(map(str, (alpha, beta))), left)
    lines = before.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.lstrip().startswith("- path:")]
    cut = next(i for i in starts if lines[i].rstrip().endswith(str(gamma)))
    nxt = next((i for i in starts if i > cut), len(lines))
    check("every other byte is kept", after == "".join(lines[:cut] + lines[nxt:]),
          repr(after))

    print("--write needs a reachable vault:")
    config(T / "no-such-vault")
    before = REG.read_text()
    rc, out, err = run("--root", str(DEV), "--remove", str(beta), "--write")
    check("an unreachable vault refuses --write with exit 1, saying so",
          rc == 1 and "vault unreachable" in err and str(T / "no-such-vault") in err
          and clean(err) and out == "", f"rc={rc} {out}{err}")
    check("and the registry is unchanged", REG.read_text() == before)
    config(VAULT)

    print("one area/name derivation, shared with records-home:")
    DEV2 = T / "dev2"
    tool = project("../dev2/apps/My_Tool", "docs/plans").resolve()
    solo = project("../dev2/solo", "docs/plans").resolve()
    rc, out, err = run("--root", DEV2, "--json")
    doc = json.loads(out) if rc == 0 else {}
    got = {c["path"]: (c["area"], c["name"]) for c in doc.get("found_not_in_registry", [])}
    want = {}
    for repo in (tool, solo):
        rrc, rout, rerr = run("--project", repo, script=RECORDS_HOME)
        home = Path(rout.strip())
        want[str(repo)] = (home.parent.name, home.name) if rrc == 0 else (rrc, rerr)
    check("scan's area and name are records-home's for the same repo (parent folder, "
          "last folder, as written)", got == want, f"scan {got} records-home {want}")
    rc, out, err = run("--root", DEV2, "--add", tool, "--add", solo, "--write")
    data = yaml.safe_load(REG.read_text())
    reg = {p["path"]: (p["area"], p["name"]) for p in data["projects"]}
    check("--add registers exactly that area and name",
          rc == 0 and all(reg.get(k) == v for k, v in want.items()),
          f"rc={rc} {reg} {out}{err}")
    for repo in (tool, solo):
        rrc, rout, _ = run("--project", repo, script=RECORDS_HOME)
        check(f"records-home resolves the registered {repo.name} to the same home",
              rrc == 0 and rout.strip() == str(VAULT / "Portfolio" / Path(*want[str(repo)])))

    print("removal keeps what belongs to the next entry:")
    REG.write_text(f"version: 1\nprojects:\n  - path: {alpha}\n    name: alpha\n"
                   f"    area: apps  # the first\n  # beta, kept by hand\n\n"
                   f"  - path: {beta}\n    name: beta\n    area: apps\n# the end\n")
    rc, out, err = run("--root", DEV, "--remove", alpha, "--write")
    check("--remove keeps the comment and blank run before the next entry",
          rc == 0 and REG.read_text() == (f"version: 1\nprojects:\n  # beta, kept by hand\n\n"
                                          f"  - path: {beta}\n    name: beta\n    area: apps\n"
                                          f"# the end\n"), f"rc={rc} {REG.read_text()!r}")
    before = REG.read_text()
    rc, out, err = run("--root", DEV, "--remove", beta)
    check("a dry-run --remove of the only entry reports the refusal, not 'would remove'",
          rc == 1 and "would remove" not in out
          and f"REFUSED --remove {beta}: it is the registry's only entry" in out
          and clean(err), f"rc={rc} {out}{err}")
    check("...and writes nothing", REG.read_text() == before)

    print("--json with an edit flag:")
    for flags in (("--add-all",), ("--remove", beta), ("--add", alpha, "--write")):
        rc, out, err = run("--root", DEV, "--json", *flags)
        check(f"--json {' '.join(map(str, flags))} is a usage error, exit 2, nothing on stdout",
              rc == 2 and out == "" and "--json" in err and clean(err), f"rc={rc} {out}{err}")
    check("...and the registry is unchanged", REG.read_text() == before)

    print("a projects root derived from the registry must be a real one:")
    for label, path in (("$HOME", HOME / "apps" / "x"), ("/", Path("/no-such-area/x")),
                        ("a root two folders deep", Path("/no-such/area/x"))):
        REG.write_text(f"version: 1\nprojects:\n  - path: {path}\n    name: x\n"
                       f"    area: area\n")
        rc, out, err = run()
        check(f"{label}: refused with exit 2 and 'pass --root'",
              rc == 2 and "pass --root" in err and clean(err) and out == "",
              f"rc={rc} {out}{err}")
        rc, out, err = run("--root", DEV)
        check(f"{label}: an explicit --root still walks", rc == 0, f"rc={rc} {err}")
    REG.write_text(before)

    print("a malformed legacy config:")
    CONFIG.write_text(json.dumps({"registry": str(REG)}))
    legacy = HOME / ".claude" / "portfolio-config.yaml"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("vault_dir: [unclosed\n")
    for flags in ((), ("--write",)):
        rc, out, err = run("--root", DEV, *flags)
        check(f"portfolio-config.yaml that does not parse{' with --write' if flags else ''}: "
              f"exit 2", rc == 2 and "does not parse" in err and clean(err) and out == "",
              f"rc={rc} {out}{err}")
    legacy.unlink()
    config(VAULT)
finally:
    shutil.rmtree(T, ignore_errors=True)

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("ALL OK")
