#!/usr/bin/env python3
"""The optional business layer: off by default, on when configured, never fatal.

The business layer is an external scanner named by the `business_scan` setting
(an argv list in obsidian-wiki's config.json; $BUSINESS_SCAN_PATH overrides it
with a script run by this interpreter). No other plugin is assumed to exist.

  absent    nothing configured, or the setting names a script that is not there:
            compass-scan's JSON carries no business keys and portfolio-rebuild
            writes no global-business.md — everything else exactly as without the
            layer — plus one loud "business layer: unavailable" line.
  present   the scanner's JSON attaches a business block per assessed project in
            compass-scan, group-aware; portfolio-rebuild pipes it through the
            `business-rollup.py` that ships beside the scanner and writes
            global-business.md, leaving the other roll-ups unaffected.
  broken    a scanner that fails or prints the wrong shape degrades to no layer,
            never a crash, and never truncates an existing roll-up.

Throwaway HOME and temp vaults only. Stdlib + PyYAML, no pytest. Run:
  python3 -I src/vault-portfolio/core/skills/portfolio/tests/test-business-degradation.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parents[1]                       # tests/ -> portfolio/ -> skills/
COMPASS_SCAN = SKILLS / "compass" / "scripts" / "compass-scan.py"
PORTFOLIO_REBUILD = SKILLS / "portfolio" / "scripts" / "portfolio-rebuild.py"

FAILURES = []


def check(cond, label):
    print(("  ok  " if cond else "  FAIL") + f"  {label}")
    if not cond:
        FAILURES.append(label)


def make_env(tmp, names=("alpha", "beta"), config_extra=None, scan_path=None):
    """A throwaway HOME + vault with `names` projects in area `apps`, the first
    carrying a business assessment. Returns (env, vault)."""
    home = tmp / "home"
    vault = tmp / "vault"
    for name in names:
        (vault / "Portfolio" / "apps" / name).mkdir(parents=True)
    biz = vault / "Portfolio" / "apps" / names[0] / "business"
    biz.mkdir()
    (biz / "BUSINESS.md").write_text(
        f"---\nschema: 1\nproject: {names[0]}\nverdict: monetize\naudience: x\n"
        "evidence: local-only\nlast_reviewed: 2026-01-01\n"
        "monetization:\n  model: paid\n  pricing: null\n  channels: []\ntargets: []\n---\n# x\n")
    repos = tmp / "dev" / "apps"
    repos.mkdir(parents=True)
    reg = "projects:\n"
    for name in names:
        (repos / name).mkdir()
        reg += f"  - name: {name}\n    area: apps\n    path: {repos / name}\n    enabled: true\n"
    registry = tmp / "registry.yaml"
    registry.write_text(reg)
    cfg = home / ".config" / "obsidian-wiki" / "config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"default_vault": str(vault), "registry": str(registry),
                               **(config_extra or {})}))
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}
    if scan_path is not None:
        env["BUSINESS_SCAN_PATH"] = str(scan_path)
    return env, vault


def run(script, env, *args):
    return subprocess.run([sys.executable, "-I", str(script), *args], capture_output=True,
                          text=True, env=env, timeout=120, stdin=subprocess.DEVNULL)


ALPHA_ASSESSED = {
    "name": "alpha", "area": "apps", "assessed": True, "verdict": "monetize",
    "monetization": {"model": "paid"}, "gtm": None, "metrics": [],
    "last_reviewed_age_days": 3,
    "research": {"exists": True, "age_days": 5},
    "plan": {"exists": False, "age_days": None},
}

ROLLUP = ("import json, sys\n"
          "doc = json.load(sys.stdin)\n"
          "print('# Global business\\n')\n"
          "for p in doc['projects']:\n"
          "    print(f\"- {p['area']}/[[{p['name']}]] — {p['verdict']}\")\n")


def fake_scanner(tmp, label, payload, rollup=True):
    """A stand-in scanner printing `payload` (a dict, or raw text), with the
    roll-up script beside it unless `rollup` is False."""
    d = tmp / f"scanner-{label}"
    d.mkdir()
    text = payload if isinstance(payload, str) else json.dumps(payload)
    (d / "business-scan.py").write_text(f"print({text!r})\n")
    if rollup:
        (d / "business-rollup.py").write_text(ROLLUP)
    return d / "business-scan.py"


# --------------------------------------------------------------------------
# compass-scan
# --------------------------------------------------------------------------
def test_compass_absent_is_unchanged(tmp):
    for label, env in (("nothing configured", make_env(tmp / "a")[0]),
                       ("a scanner that is not there",
                        make_env(tmp / "b", scan_path=tmp / "nonexistent" / "scan.py")[0])):
        r = run(COMPASS_SCAN, env)
        check(r.returncode == 0, f"compass-scan ({label}): exit 0 ({r.stderr.strip()[:120]})")
        try:
            doc = json.loads(r.stdout)
        except json.JSONDecodeError:
            doc = {}
        check(doc and not any("business" in p for p in doc.get("projects", [])),
              f"compass-scan ({label}): no per-project 'business' key — output shape unchanged")
        check({"generated", "vault_dir", "projects", "couldnt_assess"} <= set(doc),
              f"compass-scan ({label}): the envelope keys are intact")


def test_compass_present_attaches_business(tmp):
    scan = fake_scanner(tmp, "present", {"projects": [ALPHA_ASSESSED]})
    for label, env in (
            ("$BUSINESS_SCAN_PATH", make_env(tmp / "env", scan_path=scan)[0]),
            ("config.json business_scan",
             make_env(tmp / "cfg", config_extra={"business_scan": [sys.executable, str(scan)]})[0])):
        r = run(COMPASS_SCAN, env)
        check(r.returncode == 0, f"compass-scan (present via {label}): exit 0 ({r.stderr.strip()[:120]})")
        try:
            by = {p["name"]: p for p in json.loads(r.stdout)["projects"]}
        except (json.JSONDecodeError, KeyError):
            by = {}
        ab = by.get("alpha", {}).get("business", {})
        check(ab.get("verdict") == "monetize",
              f"compass-scan (present via {label}): the assessed project carries business.verdict")
        check(ab.get("research_age_days") == 5,
              f"compass-scan (present via {label}): research_age_days is an int "
              f"(artifact present) — got {ab.get('research_age_days')!r}")
        check("plan_age_days" in ab and ab.get("plan_age_days") is None,
              f"compass-scan (present via {label}): plan_age_days null (no plan) "
              f"— got {ab.get('plan_age_days')!r}")
        check("business" not in by.get("beta", {}),
              f"compass-scan (present via {label}): an unassessed project has no business key")


def test_compass_broken_business_degrades(tmp):
    """A scanner that prints valid-but-wrong-shape JSON, a top-level array or no JSON
    at all degrades to no business layer, never a crash of the whole compass lane."""
    for label, payload in [
        ("wrong-shape project", '{"projects": [{"assessed": true, "verdict": "monetize"}]}'),
        ("top-level array", "[1, 2, 3]"),
        ("not json", "this is not json at all"),
    ]:
        tag = label.replace(" ", "_")
        env, _ = make_env(tmp / tag, scan_path=fake_scanner(tmp, tag, payload))
        r = run(COMPASS_SCAN, env)
        check(r.returncode == 0, f"compass-scan (broken business: {label}): exit 0, not a crash")
        try:
            doc = json.loads(r.stdout)
            ok = "projects" in doc and not any("business" in p for p in doc["projects"])
        except json.JSONDecodeError:
            ok = False
        check(ok, f"compass-scan (broken business: {label}): valid envelope, no business keys")


# One group entry (alpha + gamma) plus one ungrouped assessed project (beta), shaped
# as a business scanner emits them. Distinct values per entry, so a mis-keyed lookup
# shows up as the wrong verdict rather than passing.
GROUP_ENTRY = {
    "name": "suite", "area": None, "group": True,
    "members": ["apps/alpha", "apps/gamma"],
    "assessed": True, "verdict": "monetize",
    "monetization": {"model": "paid"}, "gtm": {"pct": 50}, "metrics": [],
    "last_reviewed_age_days": 1,
    "research": {"exists": True, "age_days": 7},
    "plan": {"exists": False, "age_days": None},
}
UNGROUPED_ENTRY = {
    "name": "beta", "area": "apps", "assessed": True, "verdict": "later",
    "monetization": None, "gtm": None, "metrics": [],
    "last_reviewed_age_days": 3,
    "research": {"exists": False, "age_days": None},
    "plan": {"exists": False, "age_days": None},
}
EXPECT_GROUPED = {"verdict": "monetize", "model": "paid", "gtm_pct": 50,
                  "last_reviewed_age_days": 1, "research_age_days": 7,
                  "plan_age_days": None, "stage": "launched", "group": "suite"}
EXPECT_UNGROUPED = {"verdict": "later", "model": None, "gtm_pct": None,
                    "last_reviewed_age_days": 3, "research_age_days": None,
                    "plan_age_days": None, "stage": "assessed"}


def test_compass_group_aware(tmp):
    """A business group is not a registry project: it adds no project row, but each
    member carries the GROUP's business state tagged `group: <slug>`. Ungrouped
    projects keep their own block."""
    scan = fake_scanner(tmp, "groups", {"groups": ["suite"],
                                        "projects": [GROUP_ENTRY, UNGROUPED_ENTRY]})
    env, _ = make_env(tmp / "g", names=("alpha", "beta", "gamma"), scan_path=scan)
    r = run(COMPASS_SCAN, env)
    check(r.returncode == 0, f"compass-scan (groups): exit 0 ({r.stderr.strip()[:120]})")
    try:
        by = {p["name"]: p for p in json.loads(r.stdout)["projects"]}
    except (json.JSONDecodeError, KeyError):
        by = {}
    check("suite" not in by, "compass-scan (groups): the group slug is NOT a project row")
    check(set(by) == {"alpha", "beta", "gamma"},
          f"compass-scan (groups): only registry projects have rows — got {sorted(by)}")
    for member in ("alpha", "gamma"):
        check(by.get(member, {}).get("business") == EXPECT_GROUPED,
              f"compass-scan (groups): member {member} carries the group's block + group:suite "
              f"— got {by.get(member, {}).get('business')!r}")
    check(by.get("beta", {}).get("business") == EXPECT_UNGROUPED,
          f"compass-scan (groups): the ungrouped project's block has no 'group' key "
          f"— got {by.get('beta', {}).get('business')!r}")


def test_compass_no_group_keys_is_backward_compatible(tmp):
    """A scanner with no `groups`/`group`/`members` keys at all produces the plain
    per-project blocks."""
    plain_alpha = dict(UNGROUPED_ENTRY, name="alpha", verdict="monetize",
                       monetization={"model": "paid"})
    scan = fake_scanner(tmp, "plain", {"projects": [plain_alpha, UNGROUPED_ENTRY]})
    env, _ = make_env(tmp / "p", scan_path=scan)
    r = run(COMPASS_SCAN, env)
    check(r.returncode == 0, f"compass-scan (no group keys): exit 0 ({r.stderr.strip()[:120]})")
    try:
        by = {p["name"]: p for p in json.loads(r.stdout)["projects"]}
    except (json.JSONDecodeError, KeyError):
        by = {}
    check(by.get("beta", {}).get("business") == EXPECT_UNGROUPED,
          f"compass-scan (no group keys): block unchanged — got {by.get('beta', {}).get('business')!r}")
    check(by.get("alpha", {}).get("business") ==
          dict(EXPECT_UNGROUPED, verdict="monetize", model="paid", stage="modeled"),
          f"compass-scan (no group keys): assessed block unchanged "
          f"— got {by.get('alpha', {}).get('business')!r}")


# --------------------------------------------------------------------------
# portfolio-rebuild
# --------------------------------------------------------------------------
def test_rebuild_absent_writes_no_global_business(tmp):
    for label, (env, vault) in (
            ("nothing configured", make_env(tmp / "a")),
            ("a scanner that is not there",
             make_env(tmp / "b", scan_path=tmp / "nonexistent" / "business-scan.py"))):
        r = run(PORTFOLIO_REBUILD, env, "--write")
        check(r.returncode == 0, f"portfolio-rebuild ({label}): exit 0 ({r.stderr.strip()[:120]})")
        port = vault / "Portfolio"
        check((port / "global-backlog.md").exists() and (port / "global-maturity.md").exists(),
              f"portfolio-rebuild ({label}): global-backlog + global-maturity still written")
        check(not (port / "global-business.md").exists(),
              f"portfolio-rebuild ({label}): global-business.md NOT written")
        check("business layer: unavailable" in r.stdout,
              f"portfolio-rebuild ({label}): one loud 'unavailable' line ({r.stdout.strip()[-160:]})")


def test_rebuild_present_writes_global_business(tmp):
    scan = fake_scanner(tmp, "rb", {"projects": [ALPHA_ASSESSED]})
    for label, (env, vault) in (
            ("$BUSINESS_SCAN_PATH", make_env(tmp / "env", scan_path=scan)),
            ("config.json business_scan",
             make_env(tmp / "cfg", config_extra={"business_scan": [sys.executable, str(scan)]}))):
        r = run(PORTFOLIO_REBUILD, env, "--write")
        check(r.returncode == 0, f"portfolio-rebuild (present via {label}): exit 0 "
                                 f"({r.stderr.strip()[:120]})")
        gbiz = vault / "Portfolio" / "global-business.md"
        check(gbiz.exists() and "apps/[[alpha]] — monetize" in gbiz.read_text(),
              f"portfolio-rebuild (present via {label}): global-business.md written by the "
              f"roll-up beside the scanner")
        check((vault / "Portfolio" / "global-maturity.md").exists(),
              f"portfolio-rebuild (present via {label}): the other roll-ups are unaffected")
        check("global-business written: True" in r.stdout,
              f"portfolio-rebuild (present via {label}): the status line reports it")
    env, vault = make_env(tmp / "dry", scan_path=scan)
    r = run(PORTFOLIO_REBUILD, env)
    check(r.returncode == 0 and not (vault / "Portfolio" / "global-business.md").exists()
          and "global-business written: DRY-RUN" in r.stdout,
          "portfolio-rebuild (present, dry run): reports DRY-RUN and writes nothing")


def test_rebuild_no_rollup_or_failing_scanner_degrades(tmp):
    scan = fake_scanner(tmp, "norollup", {"projects": [ALPHA_ASSESSED]}, rollup=False)
    env, vault = make_env(tmp / "nr", scan_path=scan)
    r = run(PORTFOLIO_REBUILD, env, "--write")
    check(r.returncode == 0 and not (vault / "Portfolio" / "global-business.md").exists()
          and "business layer: unavailable" in r.stdout,
          f"a scanner with no business-rollup.py beside it leaves the layer unavailable "
          f"({r.stdout.strip()[-160:]})")

    failing = tmp / "scanner-fails"
    failing.mkdir()
    (failing / "business-scan.py").write_text("import sys\nsys.exit('scan blew up')\n")
    (failing / "business-rollup.py").write_text(ROLLUP)
    env, vault = make_env(tmp / "fl", scan_path=failing / "business-scan.py")
    existing = vault / "Portfolio" / "global-business.md"
    existing.write_text("# Global business\n\n- the previous good roll-up\n")
    r = run(PORTFOLIO_REBUILD, env, "--write")
    check(r.returncode == 0, f"a failing scanner does not fail the rebuild (rc={r.returncode})")
    check(existing.read_text() == "# Global business\n\n- the previous good roll-up\n",
          "...and the existing global-business.md is left intact, never truncated")
    check("global-business written: None" in r.stdout and "scan blew up" in r.stderr,
          "...and the failure is reported, not hidden")


def test_rebuild_empty_rollup_keeps_existing(tmp):
    """A roll-up that exits 0 but prints nothing usable is a failed layer, not a new
    roll-up: the existing global-business.md stays byte-identical and the status
    line does not report it written."""
    previous = "# Global business\n\n- the previous good roll-up\n"
    for label, rollup_src in (("empty stdout", "import sys\nsys.stdin.read()\n"),
                              ("blank stdout", "import sys\nsys.stdin.read()\nprint('\\n   \\n')\n"),
                              ("no roll-up heading",
                               "import sys\nsys.stdin.read()\nprint('half a table')\n")):
        tag = label.replace(" ", "-")
        scan = fake_scanner(tmp, tag, {"projects": [ALPHA_ASSESSED]}, rollup=False)
        (scan.parent / "business-rollup.py").write_text(rollup_src)
        env, vault = make_env(tmp / tag, scan_path=scan)
        existing = vault / "Portfolio" / "global-business.md"
        existing.write_text(previous)
        before = existing.read_bytes()
        r = run(PORTFOLIO_REBUILD, env, "--write")
        check(r.returncode == 0, f"rebuild ({label} roll-up): exit 0 (rc={r.returncode})")
        check(existing.read_bytes() == before,
              f"rebuild ({label} roll-up): the existing global-business.md is byte-identical")
        check("global-business written: True" not in r.stdout
              and "global-business written: None" in r.stdout,
              f"rebuild ({label} roll-up): the layer is reported failed, not written "
              f"({r.stdout.strip()[-200:]!r})")
        check("global-business.md" in r.stderr and "untouched" in r.stderr,
              f"rebuild ({label} roll-up): stderr says the file was left untouched "
              f"({r.stderr.strip()[-200:]!r})")


def test_rebuild_symlinked_scanner_finds_its_rollup(tmp):
    """The roll-up is found beside the scanner's REAL file, so a scanner reached
    through a symlink still finds the business-rollup.py it ships with."""
    scan = fake_scanner(tmp, "real", {"projects": [ALPHA_ASSESSED]})
    links = tmp / "links"
    links.mkdir()
    (links / "business-scan.py").symlink_to(scan)
    env, vault = make_env(tmp / "sym", scan_path=links / "business-scan.py")
    r = run(PORTFOLIO_REBUILD, env, "--write")
    gbiz = vault / "Portfolio" / "global-business.md"
    check(r.returncode == 0 and "global-business written: True" in r.stdout
          and gbiz.is_file() and "apps/[[alpha]] — monetize" in gbiz.read_text(),
          f"a symlinked scanner finds the roll-up beside its real file "
          f"({r.stdout.strip()[-200:]!r} {r.stderr.strip()[-200:]!r})")


def main():
    for fn in (test_compass_absent_is_unchanged,
               test_compass_present_attaches_business,
               test_compass_broken_business_degrades,
               test_compass_group_aware,
               test_compass_no_group_keys_is_backward_compatible,
               test_rebuild_absent_writes_no_global_business,
               test_rebuild_present_writes_global_business,
               test_rebuild_no_rollup_or_failing_scanner_degrades,
               test_rebuild_empty_rollup_keeps_existing,
               test_rebuild_symlinked_scanner_finds_its_rollup):
        with tempfile.TemporaryDirectory() as td:
            fn(Path(td))
    if FAILURES:
        print(f"\nFAILED — {len(FAILURES)} check(s):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("\nOK — business-layer degradation invariants hold")


if __name__ == "__main__":
    main()
