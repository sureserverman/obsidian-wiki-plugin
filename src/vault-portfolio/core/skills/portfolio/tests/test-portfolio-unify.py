#!/usr/bin/env python3
"""portfolio-unify: backlog candidates from vault plans, on the vendored plan parser.

The plan-status contract (the Status regex, what `[~]` means, the legacy heuristic,
Deferred sections, master and gate handling) has one definition: the vendored
vendor/staged_planning/plan_parser.py, tested where it is maintained. What this file
pins is unify's side of it:

  * unify takes the contract from the vendored parser and restates none of it —
    STATUS_RE, status_state() and parse_plan() are the parser's own objects, and
    no regex in unify's source repeats one of the parser's patterns;
  * unify_project() over the synthetic fixture repos: candidate counts, dedup by
    exact Source, appended entries, the backlog created when absent;
  * the stale-plan signal (--include-stale): off by default, whole-stage, bounded
    at exactly STALE_DAYS, silent for an unstamped or fresh plan, and labelled in
    the rendered entry;
  * the plan's date stamp rides along as a tag, never the 0000-00-00 sentinel;
  * main() end to end through the config (a throwaway HOME's config.json).

Throwaway HOME and temp vaults only. Stdlib + PyYAML, no pytest. Run:
  python3 -I src/vault-portfolio/core/skills/portfolio/tests/test-portfolio-unify.py
"""
from __future__ import annotations

import ast
import datetime as dt
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
SCRIPT = SCRIPTS / "portfolio-unify.py"
FIXTURES = HERE / "fixtures"

for _k in list(os.environ):
    if _k.startswith(("OBSIDIAN_", "BUSINESS_", "VAULT_CONTEXT_")):
        os.environ.pop(_k)
_HOME = tempfile.mkdtemp(prefix="unify-home-")
os.environ["HOME"] = _HOME


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load(SCRIPT, "portfolio_unify")
_config = _load(SCRIPTS / "_config.py", "_unify_test_config")
VENDORED = _config.PLUGIN_ROOT / "vendor" / "staged_planning" / "plan_parser.py"

failures: list[str] = []
BL = "BL"     # spelled apart so this file carries no literal register id


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        failures.append(name)
        print(f"FAIL  {name}  {detail}")


def expand_ids(root: Path):
    for p in root.rglob("*.md"):
        t = p.read_text(encoding="utf-8")
        p.write_text(t.replace("{DEC}", "DEC").replace("{GDEC}", "GDEC").replace("{BL}", "BL"),
                     encoding="utf-8")


# --------------------------------------------------------------------------
print("the contract comes from the vendored parser:")
pp = getattr(mod, "plan_parser", None)
check("unify exposes the parser module it loaded", pp is not None)
if pp is not None:
    check("...and it is the vendored file, not a copy elsewhere",
          Path(pp.__file__).resolve() == VENDORED.resolve(), f"got {pp.__file__}")
    for name in ("STATUS_RE", "status_state", "parse_plan", "plan_date", "stale_age_days",
                 "STALE_DAYS"):
        check(f"unify.{name} is the parser's own object",
              getattr(mod, name, None) is getattr(pp, name, object()))

src = SCRIPT.read_text(encoding="utf-8")
tree = ast.parse(src)
own_defs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
check("unify defines no parser function of its own",
      not own_defs & {"status_state", "parse_plan", "parse_plan_status", "plan_date",
                      "stale_age_days", "plan_terminal_state", "contract_warnings"},
      f"defines: {sorted(own_defs & {'status_state', 'parse_plan', 'parse_plan_status'})}")
if pp is not None:
    parser_patterns = {v.pattern for v in vars(pp).values() if isinstance(v, re.Pattern)}
    restated = []
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "compile"
                and n.args and isinstance(n.args[0], ast.Constant)
                and n.args[0].value in parser_patterns):
            restated.append(n.args[0].value)
    check("no regex in unify's source restates one of the parser's patterns",
          not restated, f"restated: {restated}")


# --------------------------------------------------------------------------
def make_home(td: Path, fixture: str, with_backlog=True):
    """A vault project home built from a fixture repo's docs/."""
    work = td / "fixture"
    shutil.copytree(FIXTURES / fixture, work)
    expand_ids(work)
    home = td / "vault" / "Portfolio" / "apps" / "example-app"
    shutil.copytree(work / "docs" / "plans", home / "plans")
    if with_backlog and (work / "docs" / "backlog.md").exists():
        shutil.copy(work / "docs" / "backlog.md", home / "backlog.md")
    return home


def unify(home, write, include_stale=False, evidence=()):
    orig = mod.git_stage_evidence
    mod.git_stage_evidence = lambda _p: list(evidence)
    try:
        return mod.unify_project(home, write, str(home), include_stale)
    finally:
        mod.git_stage_evidence = orig


print("unify_project over the synthetic repos:")
with tempfile.TemporaryDirectory() as td:
    home = make_home(Path(td), "proj-a-plans-and-backlog")
    before = (home / "backlog.md").read_text()
    n, d, c = unify(home, False)
    check("proj-a: 3 candidates, 1 duplicate, 2 new", (n, d, c) == (2, 1, 3), f"got {(n, d, c)}")
    check("proj-a: a dry run writes nothing", (home / "backlog.md").read_text() == before)
    n, d, c = unify(home, True)
    after = (home / "backlog.md").read_text()
    check("proj-a: --write appends the 2 new entries after the existing one",
          after.startswith(before) and after.count("\n## BL-") == 3, after)
    check("proj-a: the new ids continue from the highest existing one",
          f"## {BL}-002 — Add the import command" in after
          and f"## {BL}-003 — Streaming export for very large files" in after, after)
    check("proj-a: the duplicate (same Source as the hand-registered entry) is not re-added",
          after.count("— Stage 2 / Task 2.1") == 1)
    check("proj-a: an open Status task is signalled status-unexecuted",
          "Auto-unified from plan (status-unexecuted)" in after)
    check("proj-a: the Deferred bullet surfaces with its own signal",
          "Auto-unified from plan (deferred-section)" in after)
    check("proj-a: the gate bullet and the all-done plan contribute nothing",
          "round-trip" not in after and "all-done-plan" not in after)
    check("proj-a: every new entry is tagged with its plan's date stamp",
          after.count("- **Tags:** auto-unified, 2026-01-20") == 2, after)
    n2, d2, c2 = unify(home, True)
    check("proj-a: a second --write finds everything registered and appends nothing",
          (n2, d2) == (0, 3) and (home / "backlog.md").read_text() == after, f"{(n2, d2, c2)}")

with tempfile.TemporaryDirectory() as td:
    home = make_home(Path(td), "proj-b-plans-only")
    check("proj-b: fixture sanity — no backlog yet", not (home / "backlog.md").exists())
    n, d, c = unify(home, True)
    text = (home / "backlog.md").read_text() if (home / "backlog.md").exists() else ""
    check("proj-b: 3 legacy candidates, all new", (n, d, c) == (3, 0, 3), f"got {(n, d, c)}")
    check("proj-b: the backlog is created with the standard header",
          text.startswith(mod.HEADER), text[:120])
    check("proj-b: each entry is unchecked-open",
          text.count("Auto-unified from plan (unchecked-open)") == 3)
    check("proj-b: ids start at 001", f"## {BL}-001 — read the settings file" in text, text)

with tempfile.TemporaryDirectory() as td:
    home = Path(td) / "vault" / "Portfolio" / "apps" / "example-bare"
    home.mkdir(parents=True)
    check("a home with no plans/ yields nothing and writes nothing",
          unify(home, True) == (0, 0, 0) and not (home / "backlog.md").exists())


# --------------------------------------------------------------------------
print("plan enumeration — the one shared definition:")
ONE_OPEN = ("# Project Plan: {t}\n\n## Stage 1: S\n\n### Task 1.1: {t} task\n"
            "- **Status:** [ ]\n")
with tempfile.TemporaryDirectory() as td:
    home = Path(td) / "vault" / "Portfolio" / "apps" / "example-app"
    plans = home / "plans"
    (plans / "2026-02-01-set").mkdir(parents=True)
    (plans / "2026-02-01-set" / "01-phase.md").write_text(ONE_OPEN.format(t="nested"))
    (plans / "2026-02-02-top-plan.md").write_text(ONE_OPEN.format(t="top"))
    # plan-status-audit --fix keeps its backups inside plans/; they are copies of
    # plans already counted, never plans of their own.
    bak = plans / ".audit-backups" / "20260202-120000"
    bak.mkdir(parents=True)
    (bak / "2026-02-02-top-plan.md").write_text(ONE_OPEN.format(t="top"))
    n, d, c = unify(home, True)
    body = (home / "backlog.md").read_text() if (home / "backlog.md").exists() else ""
    check("a nested plan contributes its open task", "nested task" in body, body)
    check("a plan-status backup copy contributes nothing",
          ".audit-backups" not in body and (n, d, c) == (2, 0, 2), f"{(n, d, c)}\n{body}")

with tempfile.TemporaryDirectory() as td:
    # Documents that live in plans/ but are not plans: the one shared exclusion,
    # portfolio-rebuild's not_a_plan(), which compass and plan-status-audit use too.
    home = Path(td) / "vault" / "Portfolio" / "apps" / "example-app"
    plans = home / "plans"
    plans.mkdir(parents=True)
    (plans / "2026-02-02-top-plan.md").write_text(ONE_OPEN.format(t="top"))
    others = ("README.md", "backlog.md", "2026-02-03-widget-design.md",
              "2026-02-04-store-architecture.md", "2026-02-05-old-done.md")
    for name in others:
        (plans / name).write_text(ONE_OPEN.format(t=name))
    n, d, c = unify(home, True)
    body = (home / "backlog.md").read_text() if (home / "backlog.md").exists() else ""
    check("README.md, backlog.md and design, architecture and done documents in plans/ "
          "contribute nothing", (n, d, c) == (1, 0, 1)
          and not any(name in body for name in others), f"{(n, d, c)}\n{body}")
    nap = getattr(mod.pr, "not_a_plan", None)
    check("not_a_plan() names each of them, and not the plan",
          nap is not None and all(nap(plans / name) for name in others)
          and not nap(plans / "2026-02-02-top-plan.md"))

pr_mod = mod.pr
plan_files = getattr(pr_mod, "plan_files", None)
check("portfolio-rebuild defines the one plan enumeration, plan_files()", callable(plan_files))
psa_src = (SCRIPTS / "plan-status-audit.py").read_text(encoding="utf-8")
compass_src = (SCRIPTS.parents[1] / "compass" / "scripts" / "compass-scan.py").read_text(
    encoding="utf-8")
for label, text in (("portfolio-unify.py", src), ("plan-status-audit.py", psa_src),
                    ("compass-scan.py", compass_src)):
    t = ast.parse(text)
    calls = {getattr(n.func, "attr", getattr(n.func, "id", "")) for n in ast.walk(t)
             if isinstance(n, ast.Call)}
    check(f"{label} enumerates plans through plan_files()", "plan_files" in calls)
    check(f"{label} decides what is not a plan through not_a_plan()", "not_a_plan" in calls)
for label, text in (("portfolio-unify.py", src), ("compass-scan.py", compass_src)):
    t = ast.parse(text)
    globs = [n.lineno for n in ast.walk(t) if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") in ("glob", "rglob", "iterdir", "walk")]
    check(f"{label} walks no directory of its own", not globs, f"at lines {globs}")


# --------------------------------------------------------------------------
print("the stale-plan signal:")
LEGACY = ("# Project Plan: {t}\n\n## Stage 1: S\n\n### Task 1.1: T\n"
          "- [ ] a suppressed unresolved item\n- [ ] a second suppressed item\n\n"
          "## Stage 2: U\n\n### Task 2.1: V\n- [ ] an item in a stage with no evidence\n")


def stale_run(fname, include_stale, evidence, write=False):
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "h"
        (home / "plans").mkdir(parents=True)
        (home / "plans" / fname).write_text(LEGACY.format(t=fname))
        res = unify(home, write, include_stale, evidence)
        body = (home / "backlog.md").read_text() if (home / "backlog.md").exists() else ""
        return res, body


OLD = "2020-01-01-old-plan.md"
DONE1 = {("2026-01-01", 1)}               # a commit after the plan marks Stage 1 executed
(_, _, off), _ = stale_run(OLD, False, DONE1)
(_, _, on), body = stale_run(OLD, True, DONE1, write=True)
check("flag OFF: a git-suppressed stage of an old plan stays silent", off == 1, f"got {off}")
check("flag ON: the old plan's suppressed items surface", on == 3, f"got {on}")
check("...rendered with the stale-plan-unchecked signal",
      body.count("(stale-plan-unchecked)") == 2, body)
check("...and tagged with the plan's date stamp", body.count("auto-unified, 2020-01-01") == 3, body)
(_, _, every), _ = stale_run(OLD, True, set())
check("the stale diff is whole-stage: with no evidence every item surfaces once",
      every == on, f"no-evidence={every} flag-on={on}")

today = dt.date.today()
for days, stale in ((mod.STALE_DAYS, False), (mod.STALE_DAYS + 1, True), (0, False)):
    name = f"{(today - dt.timedelta(days=days)).isoformat()}-boundary-plan.md"
    ev = {(today.isoformat(), 1)}
    (_, _, o), _ = stale_run(name, False, ev)
    (_, _, s), _ = stale_run(name, True, ev)
    check(f"a plan {days} days old is {'stale' if stale else 'not stale'}",
          (s > o) == stale, f"off={o} on={s}")

(_, _, o), _ = stale_run("unstamped-plan.md", False, DONE1)
(_, _, s), body = stale_run("unstamped-plan.md", True, DONE1, write=True)
check("an unstamped plan has unknown age and contributes no stale items", s == o, f"{o} vs {s}")
check("...and its entries carry no fake date tag",
      body and all(ln.strip() == "- **Tags:** auto-unified"
                   for ln in body.splitlines() if ln.startswith("- **Tags:**")), body)


# --------------------------------------------------------------------------
print("main() through the config:")
with tempfile.TemporaryDirectory() as td:
    tdp = Path(td)
    home_dir = tdp / "home"
    vault = tdp / "vault"
    work = tdp / "repos" / "example-app"
    shutil.copytree(FIXTURES / "proj-a-plans-and-backlog", work)
    expand_ids(work)
    phome = vault / "Portfolio" / "apps" / "example-app"
    shutil.copytree(work / "docs" / "plans", phome / "plans")
    shutil.copy(work / "docs" / "backlog.md", phome / "backlog.md")
    reg = tdp / "registry.yaml"
    reg.write_text(f"projects:\n  - name: example-app\n    area: apps\n    path: {work}\n"
                   f"  - name: example-off\n    area: apps\n    path: {tdp / 'off'}\n"
                   f"    enabled: false\n")
    cfg = home_dir / ".config" / "obsidian-wiki" / "config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"default_vault": str(vault), "registry": str(reg)}))
    env = {"HOME": str(home_dir), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    r = subprocess.run([sys.executable, "-I", str(SCRIPT)], capture_output=True, text=True,
                       env=env, timeout=120)
    check("a dry run reports the totals over the enabled projects",
          r.returncode == 0 and "DRY-RUN: 2 new entries, 1 duplicates skipped, 3 candidates "
          "across 1 projects" in r.stdout, r.stdout + r.stderr)
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--write", "--project", str(work)],
                       capture_output=True, text=True, env=env, timeout=120)
    check("--write --project appends to that project's vault backlog",
          r.returncode == 0 and (phome / "backlog.md").read_text().count("\n## BL-") == 3,
          r.stdout + r.stderr)

    def vault_state():
        return sorted((q.relative_to(vault).as_posix(), q.read_bytes() if q.is_file() else b"")
                      for q in vault.rglob("*"))

    # An unmatched --project is refused before any write, never a run over 0 projects.
    nowhere = tdp / "repos" / "not-registered"
    for script in (SCRIPT, SCRIPTS / "portfolio-migrate.py"):
        before = vault_state()
        r = subprocess.run([sys.executable, "-I", str(script), "--write", "--project",
                            str(nowhere)], capture_output=True, text=True, env=env, timeout=120)
        check(f"{script.name}: an unmatched --project is refused, naming the path",
              r.returncode != 0 and f"not in registry: {nowhere}" in r.stderr
              and "Traceback" not in r.stderr, f"rc={r.returncode} {r.stdout + r.stderr}")
        check(f"{script.name}: ...and the vault is unchanged", vault_state() == before)

    # A disabled project IS in the registry; saying otherwise sends the operator to
    # re-register a project that is merely switched off. Refused all the same,
    # before any write, with docs present that a run would otherwise act on.
    off = tdp / "off"
    (off / "docs" / "plans").mkdir(parents=True)
    (off / "docs" / "plans" / "2026-01-20-off-plan.md").write_text(
        "# Project Plan: off\n\n## Stage 1: S\n\n### Task 1.1: T\n- **Status:** [ ]\n")
    off_vault = vault / "Portfolio" / "apps" / "example-off"
    (off_vault / "plans").mkdir(parents=True)
    (off_vault / "plans" / "2026-01-20-off-plan.md").write_text(
        (off / "docs" / "plans" / "2026-01-20-off-plan.md").read_text())

    def repo_state():
        return sorted((q.relative_to(off).as_posix(), q.read_bytes() if q.is_file() else b"")
                      for q in off.rglob("*"))

    for script in (SCRIPT, SCRIPTS / "portfolio-migrate.py"):
        for flags in (["--write"], []):
            before, rbefore = vault_state(), repo_state()
            r = subprocess.run([sys.executable, "-I", str(script), *flags, "--project", str(off)],
                               capture_output=True, text=True, env=env, timeout=120)
            mode = "--write" if flags else "a dry run"
            check(f"{script.name} ({mode}): a disabled --project is refused as disabled",
                  r.returncode != 0 and f"disabled in the registry: {off}" in r.stderr
                  and "not in registry" not in r.stderr and "Traceback" not in r.stderr,
                  f"rc={r.returncode} {r.stdout + r.stderr}")
            check(f"{script.name} ({mode}): ...and nothing is written",
                  vault_state() == before and repo_state() == rbefore)

    # The same project spelled another way is the same project: both sides are
    # normalised (~ expanded, resolved, trailing slash dropped) before comparing.
    tilde_cfg = tdp / ".config" / "obsidian-wiki" / "config.json"
    tilde_cfg.parent.mkdir(parents=True)
    tilde_cfg.write_text(cfg.read_text())
    tilde_env = dict(env, HOME=str(tdp))
    for label, arg, e in (("a trailing slash", str(work) + "/", env),
                          ("a ~ form", "~/repos/example-app", tilde_env)):
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--project", arg],
                           capture_output=True, text=True, env=e, timeout=120)
        check(f"--project in {label} matches the registered path",
              r.returncode == 0 and "across 1 projects" in r.stdout, r.stdout + r.stderr)
    tilde_reg = tdp / "registry-tilde.yaml"
    tilde_reg.write_text("projects:\n  - name: example-app\n    area: apps\n"
                         "    path: ~/repos/example-app/\n")
    tilde_cfg.write_text(json.dumps({"default_vault": str(vault), "registry": str(tilde_reg)}))
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--project", str(work)],
                       capture_output=True, text=True, env=tilde_env, timeout=120)
    check("a registry path in ~ form with a trailing slash matches the plain --project path",
          r.returncode == 0 and "across 1 projects" in r.stdout, r.stdout + r.stderr)
    r = subprocess.run([sys.executable, "-I", str(SCRIPTS / "portfolio-migrate.py"),
                        "--project", str(work) + "/"],
                       capture_output=True, text=True, env=tilde_env, timeout=120)
    check("portfolio-migrate.py: the same normalised match (dry run)",
          r.returncode == 0 and "not in registry" not in r.stderr, r.stdout + r.stderr)


shutil.rmtree(_HOME, ignore_errors=True)
print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("OK — unify reads plans through the vendored parser and registers what it finds")
