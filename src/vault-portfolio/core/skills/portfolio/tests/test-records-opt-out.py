#!/usr/bin/env python3
"""`records: repo` is honoured by every script that derives a vault home.

A registry entry that sets `records: repo` keeps its plans, backlog, decisions and
maturity checklist in its own repo. records-home answers exit 3 for it; every other
script must agree, or a public project that opted out gets a vault home written
into its sidecar, its docs moved into the vault, or a stale vault folder read back
as its state. One predicate (portfolio-rebuild's records_in_repo) decides it, and
one validator (load_projects) refuses any other `records` value.

Each script runs as a subprocess on a throwaway HOME, vault and projects root:

  * rebuild --write writes no sidecar block into the opted-out repo, and its
    roll-ups and integration read skip the opted-out entry's vault folder;
  * migrate --all --write moves nothing of it, and --project names it as opted out;
  * unify --write leaves its vault folder alone, and --project names it;
  * integrate never reads an integration.md or backlog under its vault folder;
  * compass-scan, security-scan and plan-status-audit list it as not assessed,
    with the reason, and read nothing under its vault folder;
  * domain-decisions --promote refuses to derive a vault home for it;
  * a `records:` value other than `repo` is refused by every script.

Stdlib + PyYAML, no pytest. Run:
  python3 -I src/vault-portfolio/core/skills/portfolio/tests/test-records-opt-out.py
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
ROOT = HERE.parents[2]
RECORDS_HOME = ROOT / "scripts" / "records-home.py"
COMPASS = ROOT / "skills" / "compass" / "scripts" / "compass-scan.py"

FAILURES: list[str] = []
DEC = "DEC"   # spelled apart so this file carries no literal register id
BL = "BL"

OPEN_PLAN = ("# Project Plan: {t}\n\n## Stage 1: S\n\n### Task 1.1: {t} task\n"
             "- **Status:** [ ]\n")
OPT_OUT = "records: repo"


def check(ok, msg):
    print(f"  {'ok' if ok else 'FAIL'}: {msg}")
    if not ok:
        FAILURES.append(msg)


def digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(root).as_posix().encode() + b"\0")
        if p.is_file() and not p.is_symlink():
            h.update(p.read_bytes())
    return h.hexdigest()


class World:
    """tmp/home (HOME), tmp/vault, tmp/registry.yaml, tmp/dev/apps/<name> (git repos).

    example-app is an ordinary entry; example-lib sets `records: repo`. With
    `stale`, both have a vault folder, and example-lib's holds a plan, a backlog
    with an integration item, a maturity checklist, a decisions register, a
    security history and an integration.md that does NOT parse: a script that
    reads anything under the opted-out folder either refuses or lists it.
    """

    def __init__(self, tmp: Path, stale: bool, records="repo"):
        self.tmp = tmp
        self.home = tmp / "home"
        self.vault = tmp / "vault"
        self.registry = tmp / "registry.yaml"
        (self.vault / "Portfolio").mkdir(parents=True)
        cfg = self.home / ".config" / "obsidian-wiki" / "config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"default_vault": str(self.vault),
                                   "registry": str(self.registry)}))
        self.app = self.repo("example-app")
        self.lib = self.repo("example-lib")
        (self.lib / ".claude").mkdir()
        (self.lib / ".claude" / "vault-context.md").write_text("# notes kept by hand\n")
        self.registry.write_text(
            "version: 1\nprojects:\n"
            f"  - path: {self.app}\n    name: example-app\n    area: apps\n    enabled: true\n"
            f"  - path: {self.lib}\n    name: example-lib\n    area: apps\n    enabled: true\n"
            f"    records: {records}\n")
        self.app_home = self.vault / "Portfolio" / "apps" / "example-app"
        self.lib_home = self.vault / "Portfolio" / "apps" / "example-lib"
        if stale:
            self.stale()

    def repo(self, name):
        path = self.tmp / "dev" / "apps" / name
        (path / "docs" / "plans").mkdir(parents=True)
        (path / "docs" / "plans" / f"2026-01-01-{name}-plan.md").write_text(
            OPEN_PLAN.format(t=name))
        (path / "docs" / "backlog.md").write_text("# Backlog\n")
        env = {"HOME": str(self.home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
               "GIT_CONFIG_NOSYSTEM": "1"}
        git = ["git", "-c", "user.email=t@example.com", "-c", "user.name=t",
               "-c", "core.hooksPath=/dev/null"]
        for cmd in (git + ["init", "-q", "--template="],
                    git + ["commit", "-q", "--allow-empty", "-m", "init", "--no-verify"]):
            subprocess.run(cmd, cwd=path, env=env, check=True, capture_output=True)
        return path

    def stale(self):
        for home, name in ((self.app_home, "example-app"), (self.lib_home, "example-lib")):
            (home / "plans").mkdir(parents=True)
            (home / "plans" / f"2026-01-01-{name}-plan.md").write_text(
                OPEN_PLAN.format(t=name))
            (home / "backlog.md").write_text(
                f"# Backlog\n\n## {BL}-001 — {name} item\n\n- **Tags:** integration\n"
                f"- **Integration:** from={name} edge={name}-edge\n")
            (home / "MATURITY.md").write_text("# Maturity\n\n## Documentation\n\n- [x] a\n")
            (home / "decisions.md").write_text(
                f"# Decisions\n\n## {DEC}-001 — {name} decision\n\n"
                "- **Decided:** 2026-01-01\n- **Status:** accepted\n- **Domains:** rust\n"
                "- **Source:** a review\n- **Reason:** Because it binds.\n")
            (home / "security").mkdir()
            (home / "security" / "history.jsonl").write_text(
                json.dumps({"run_id": "20260101-1200-x", "counts": {"critical": 1}}) + "\n")
        (self.lib_home / "integration.md").write_text("---\ndepends_on: [\"[[x]]\"\n---\n")

    def env(self):
        return {"HOME": str(self.home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}

    def run(self, script, *args):
        r = subprocess.run([sys.executable, "-I", str(script), *map(str, args)],
                           capture_output=True, text=True, timeout=120, env=self.env(),
                           cwd="/", stdin=subprocess.DEVNULL)
        return r.returncode, r.stdout, r.stderr


def world(stale, **kw):
    td = tempfile.TemporaryDirectory()
    return td, World(Path(td.name).resolve(), stale, **kw)


def script(name):
    return SCRIPTS / f"{name}.py"


# --------------------------------------------------------------------------
def case_rebuild():
    print("rebuild --write: no vault home is written into an opted-out repo")
    td, w = world(stale=False)
    with td:
        sidecar = w.lib / ".claude" / "vault-context.md"
        before = sidecar.read_bytes()
        rc, out, err = w.run(script("portfolio-rebuild"), "--write")
        check(rc == 0, f"rebuild --write exits 0 (rc={rc}: {err.strip()[-300:]})")
        check(sidecar.read_bytes() == before,
              f"the opted-out repo's sidecar is byte-identical, no block appended "
              f"({sidecar.read_text()[:200]!r})")
        app_sc = w.app / ".claude" / "vault-context.md"
        check(app_sc.is_file() and str(w.app_home) in app_sc.read_text(),
              "the ordinary repo still gets its block (the skip is scoped)")
        check("sidecars enriched: 1 |" in out, f"the status line counts one sidecar ({out.strip()})")
    td, w = world(stale=True)
    with td:
        rc, out, err = w.run(script("portfolio-rebuild"), "--write")
        check(rc == 0, f"with a stale opted-out vault folder holding a broken integration.md, "
                       f"rebuild does not read it (rc={rc}: {err.strip()[-300:]})")
        for roll in ("global-backlog.md", "global-maturity.md", "global-decisions.md"):
            f = w.vault / "Portfolio" / roll
            text = f.read_text() if f.is_file() else ""
            check(f.is_file() and "example-app" in text and "example-lib" not in text,
                  f"{roll} lists the ordinary entry and not the opted-out one")


def case_migrate():
    print("migrate: an opted-out entry's docs never move")
    td, w = world(stale=False)
    with td:
        lib_before = digest(w.lib)
        rc, out, err = w.run(script("portfolio-migrate"), "--all", "--write")
        check(rc == 0, f"migrate --all --write exits 0 (rc={rc}: {err.strip()[-300:]})")
        check(digest(w.lib) == lib_before, "the opted-out repo is byte-identical")
        check(not w.lib_home.exists(), "no vault folder is created for it")
        check((w.app_home / "plans").is_dir() and not (w.app / "docs").exists(),
              "the ordinary entry is migrated (the skip is scoped)")
        check("example-lib" not in out, f"the run does not list the opted-out entry ({out!r})")
    td, w = world(stale=False)
    with td:
        before = digest(w.tmp)
        rc, out, err = w.run(script("portfolio-migrate"), "--project", w.lib, "--write")
        check(rc != 0 and OPT_OUT in err and "Traceback" not in err,
              f"--project on the opted-out repo is refused, naming the opt-out "
              f"(rc={rc}: {err.strip()[:200]})")
        check(digest(w.tmp) == before, "...and nothing is written")


def case_unify():
    print("unify: an opted-out entry's vault folder is not read or appended to")
    td, w = world(stale=True)
    with td:
        lib_before = digest(w.lib_home)
        rc, out, err = w.run(script("portfolio-unify"), "--write")
        check(rc == 0, f"unify --write exits 0 (rc={rc}: {err.strip()[-300:]})")
        check(digest(w.lib_home) == lib_before, "the opted-out vault folder is byte-identical")
        check("apps/example-lib" not in out and "apps/example-app" in out,
              f"only the ordinary entry is reported ({out.strip()})")
        before = digest(w.tmp)
        rc, out, err = w.run(script("portfolio-unify"), "--project", w.lib, "--write")
        check(rc != 0 and OPT_OUT in err and "Traceback" not in err,
              f"--project on the opted-out repo is refused (rc={rc}: {err.strip()[:200]})")
        check(digest(w.tmp) == before, "...and nothing is written")


def case_integrate():
    print("integrate: nothing under an opted-out vault folder is read")
    td, w = world(stale=True)
    with td:
        rc, out, err = w.run(script("portfolio-integrate"), "--write")
        check(rc == 0, f"a broken integration.md in the opted-out folder does not refuse "
                       f"the run (rc={rc}: {err.strip()[-300:]})")
        ib = w.vault / "Portfolio" / "integration-backlog.md"
        text = ib.read_text() if ib.is_file() else ""
        check("example-app-edge" in text and "example-lib" not in text,
              "the integration backlog rolls up the ordinary entry only")


def case_readers():
    print("compass-scan, security-scan, plan-status-audit: listed as not assessed")
    td, w = world(stale=True)
    with td:
        before = digest(w.tmp)
        rc, out, err = w.run(COMPASS)
        doc = json.loads(out) if rc == 0 else {}
        names = [p["name"] for p in doc.get("projects", [])]
        skipped = {c["name"]: c["reason"] for c in doc.get("couldnt_assess", [])}
        check(rc == 0 and names == ["example-app"],
              f"compass assesses only the ordinary entry (rc={rc}: {names} {err[-200:]})")
        check(OPT_OUT in (skipped.get("example-lib") or ""),
              f"...and lists the opted-out one with its reason ({skipped})")

        rc, out, err = w.run(script("security-scan"))
        doc = json.loads(out) if rc == 0 else {}
        names = [p["name"] for p in doc.get("projects", [])]
        skipped = {c["name"]: c["reason"] for c in doc.get("couldnt_assess", [])}
        check(rc == 0 and names == ["example-app"],
              f"security-scan reads only the ordinary entry's history (rc={rc}: {names})")
        check(OPT_OUT in (skipped.get("example-lib") or ""),
              f"...and lists the opted-out one with its reason ({skipped})")

        rc, out, err = w.run(script("plan-status-audit"), "--json")
        doc = json.loads(out) if rc == 0 else {}
        paths = [e["path"] for v in doc.get("classes", {}).values() for e in v]
        check(rc == 0 and paths and not any("example-lib" in p for p in paths),
              f"plan-status-audit classifies no plan under the opted-out folder "
              f"(rc={rc}: {paths} {err[-200:]})")
        row = [p for p in doc.get("projects", []) if p["name"] == "example-lib"]
        check(row and row[0]["count"] == 0 and OPT_OUT in (row[0]["note"] or ""),
              f"...and its project row says why ({row})")
        check(digest(w.tmp) == before, "the three readers write nothing")


def case_domain_decisions():
    print("domain-decisions --promote: no vault home is derived for an opted-out entry")
    td, w = world(stale=True)
    with td:
        args = ("--promote", f"{DEC}-001", "--area", "apps", "--name", "example-lib",
                "--domain", "rust", "--reason", "Every project on it is bound.")
        before = digest(w.tmp)
        rc, out, err = w.run(script("domain-decisions"), *args)
        check(rc == 1 and OPT_OUT in err and "Traceback" not in err,
              f"refused, naming the opt-out (rc={rc}: {err.strip()[:200]})")
        rc, out, err = w.run(script("domain-decisions"), *args[:6], "--home", w.lib_home,
                             *args[6:])
        check(rc == 0, f"an explicit --home is still honoured (rc={rc}: {err.strip()[:200]})")
        rc, out, err = w.run(script("domain-decisions"), "--promote", f"{DEC}-001", "--area",
                             "apps", "--name", "example-app", *args[6:])
        check(rc == 0, f"the ordinary entry still promotes (rc={rc}: {err.strip()[:200]})")
        check(digest(w.tmp) == before, "dry runs write nothing")


def case_bad_value():
    print("a `records:` value other than `repo` is refused by every script")
    runs = [
        ("portfolio-rebuild", script("portfolio-rebuild"), ()),
        ("portfolio-rebuild --write", script("portfolio-rebuild"), ("--write",)),
        ("portfolio-migrate --all", script("portfolio-migrate"), ("--all",)),
        ("portfolio-unify", script("portfolio-unify"), ()),
        ("portfolio-integrate", script("portfolio-integrate"), ()),
        ("portfolio-scan", script("portfolio-scan"), ()),
        ("plan-status-audit", script("plan-status-audit"), ("--json",)),
        ("security-scan", script("security-scan"), ()),
        ("compass-scan", COMPASS, ()),
        ("domain-decisions --promote", script("domain-decisions"),
         ("--promote", f"{DEC}-001", "--area", "apps", "--name", "example-app",
          "--domain", "rust", "--reason", "Bound.")),
        ("records-home", RECORDS_HOME, ("--project", "APP")),
        ("records-home --all-homes", RECORDS_HOME, ("--all-homes",)),
    ]
    td, w = world(stale=True, records="vault")
    with td:
        before = digest(w.tmp)
        for label, path, args in runs:
            args = [str(w.app) if a == "APP" else a for a in args]
            rc, out, err = w.run(path, *args)
            check(rc != 0 and "records" in err and "repo" in err and "Traceback" not in err,
                  f"{label}: refused, naming the field and the one value "
                  f"(rc={rc}: {err.strip()[:160]})")
        check(digest(w.tmp) == before, "nothing is written by any of them")


def main():
    for case in (case_rebuild, case_migrate, case_unify, case_integrate, case_readers,
                 case_domain_decisions, case_bad_value):
        case()
    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed")
        sys.exit(1)
    print("OK — every script honours `records: repo`")


if __name__ == "__main__":
    main()
