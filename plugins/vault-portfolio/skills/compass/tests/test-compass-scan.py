#!/usr/bin/env python3
"""Fixture suite for compass-scan.py. Run directly:
    python3 -I src/vault-portfolio/core/skills/compass/tests/test-compass-scan.py

Builds a throwaway HOME whose obsidian-wiki config names a copy of the fixture
vault and whose registry points at throwaway repos, runs the scanner as a
subprocess under a scrubbed environment, and asserts the JSON contract: envelope
keys, the unconfigured and unreachable refusals, plan-state extraction, signal
collectors, the couldnt_assess partition, the business layer and the read-only
guarantee. Nothing here reads the machine's real config, registry or vault.

Fixture ids are placeholders (`{BL}-001`, `{DEC}-002`), the convention of the
portfolio tests' fixtures/README.md: the copy step expands them, so the committed
tree carries no id that looks like a real register entry.

Stdlib + PyYAML, no pytest.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "compass-scan.py"
FIXTURES = HERE / "fixtures"
ID_PLACEHOLDERS = (("{GDEC}", "GDEC"), ("{DEC}", "DEC"), ("{BL}", "BL"))

# Each project entry's decision-register summary key, spelled as a keyword the way
# compass-scan.py spells it.
(DECISIONS_KEY,) = dict(decisions=None)

FAILURES = []


def expand_ids(text):
    for placeholder, prefix in ID_PLACEHOLDERS:
        text = text.replace(placeholder, prefix)
    return text


def check(cond, label):
    print(("  ok  " if cond else "  FAIL") + f"  {label}")
    if not cond:
        FAILURES.append(label)


def tree_digest(root):
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            h.update(p.as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def base_env(home, **extra):
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    env.update({k: str(v) for k, v in extra.items()})
    return env


def run_scan(home, expect_ok=True, **extra):
    r = subprocess.run([sys.executable, "-I", str(SCRIPT)],
                       capture_output=True, text=True, env=base_env(home, **extra))
    if expect_ok:
        assert r.returncode == 0, f"scanner failed (rc {r.returncode}):\n{r.stderr}"
        return json.loads(r.stdout)
    return r


def copy_vault(dest):
    shutil.copytree(FIXTURES / "vault", dest)
    for p in dest.rglob("*.md"):
        p.write_text(expand_ids(p.read_text()))


def make_env(tmp):
    """Fixture HOME + vault: copy the vault tree, write config and registry."""
    home = tmp / "home"
    vault = tmp / "vault"
    cfg_dir = home / ".config" / "obsidian-wiki"
    cfg_dir.mkdir(parents=True)
    copy_vault(vault)
    (cfg_dir / "config.json").write_text(json.dumps({"default_vault": str(vault)}))

    # repos: example-app is a real git repo with a fixed-date commit;
    # example-lib is a plain dir (non-git); example-missing's path doesn't exist
    app_repo = tmp / "dev" / "apps" / "example-app"
    app_repo.mkdir(parents=True)
    (app_repo / "README.md").write_text("example-app\n")
    env = dict(base_env(home),
               GIT_AUTHOR_DATE="2026-01-01T12:00:00 +0000",
               GIT_COMMITTER_DATE="2026-01-01T12:00:00 +0000",
               GIT_CONFIG_NOSYSTEM="1")
    git = ["git", "-c", "user.email=t@example.com", "-c", "user.name=t",
           "-c", "core.hooksPath=/dev/null"]
    for cmd in (git + ["init", "-q", "--template="],
                git + ["add", "-A"],
                git + ["commit", "-qm", "init", "--no-verify"]):
        subprocess.run(cmd, cwd=app_repo, env=env, check=True, capture_output=True)
    lib_repo = tmp / "dev" / "apps" / "example-lib"
    lib_repo.mkdir(parents=True)
    (lib_repo / "notes.txt").write_text("not a git repo\n")
    # example-broken carries only a corrupt decisions register — it exists to
    # prove a broken register degrades into errors[] instead of dropping the project
    broken_repo = tmp / "dev" / "apps" / "example-broken"
    broken_repo.mkdir(parents=True)
    (broken_repo / "notes.txt").write_text("not a git repo\n")

    (cfg_dir / "projects-registry.yaml").write_text(f"""\
projects:
  - name: example-app
    area: apps
    path: {app_repo}
    enabled: true
  - name: example-lib
    area: apps
    path: {lib_repo}
    enabled: true
  - name: example-broken
    area: apps
    path: {broken_repo}
    enabled: true
  - name: example-missing
    area: apps
    path: {tmp}/dev/apps/example-missing
    enabled: true
  - name: example-off
    area: apps
    path: {tmp}/dev/apps/example-off
    enabled: false
""")
    return home, vault


def test_envelope_and_refusals(tmp):
    print("[envelope]")
    home, vault = make_env(tmp)
    before = tree_digest(vault)
    out = run_scan(home)
    for key in ("generated", "vault_dir", "projects", "couldnt_assess"):
        check(key in out, f"envelope has '{key}'")
    names = {p["name"] for p in out["projects"]}
    check("example-app" in names, "example-app assessed")
    check("example-off" not in names, "disabled project excluded")
    ca = {c["name"]: c for c in out["couldnt_assess"]}
    check("example-missing" in ca and "not exist" in ca["example-missing"]["reason"],
          "missing path lands in couldnt_assess with reason")
    check(len(out["projects"]) + len(out["couldnt_assess"]) == 4,
          "projects + couldnt_assess partition the enabled registry")
    check(tree_digest(vault) == before, "vault tree unmodified (read-only)")

    print("[unconfigured]")
    empty = tmp / "empty-home"
    empty.mkdir()
    r = run_scan(empty, expect_ok=False)
    check(r.returncode != 0, "unconfigured exits non-zero")
    check("portfolio not configured" in (r.stderr + r.stdout),
          "unconfigured names the fix")
    check(r.stdout.strip() == "", "unconfigured prints no JSON document")

    print("[unreachable]")
    # A vault that is set but has no Portfolio/ is what an unmounted mountpoint
    # looks like. An empty `projects` list there would read as "nothing in flight
    # anywhere", so the scan must refuse with nothing on stdout.
    hollow = tmp / "hollow"
    hollow.mkdir()
    r = run_scan(home, expect_ok=False, OBSIDIAN_VAULT_PATH=hollow)
    check(r.returncode != 0, f"unreachable vault exits non-zero (rc {r.returncode})")
    check(r.stdout.strip() == "", "unreachable vault prints no JSON document")
    check("unreachable" in r.stderr, f"and says why ({r.stderr.strip()[:120]!r})")

    print("[registry without projects key]")
    (home / ".config" / "obsidian-wiki" / "projects-registry.yaml").write_text("other: 1\n")
    r = run_scan(home, expect_ok=False)
    check(r.returncode != 0 and "portfolio not configured" in r.stderr,
          "a registry with no 'projects' key is refused, not read as empty")


def test_plan_state(tmp):
    print("[plan_state]")
    home, vault = make_env(tmp)
    out = run_scan(home)
    projects = {p["name"]: p for p in out["projects"]}
    plans_a = {p["file"]: p for p in projects["example-app"]["plans"]}

    widget = plans_a["2026-06-01-widget-plan.md"]
    check(widget["active"] is True, "open plan is active")
    check(widget["stage"] == 2, "open plan reports current stage 2")
    check(widget["next_task"] == "Task 2.2: Install windows",
          "next unchecked task surfaced")
    check((widget["done"], widget["total"]) == (3, 4), "task counts 3/4")

    shed = plans_a["2026-05-01-shed-plan.md"]
    check(shed["active"] is False, "closed plan inactive")
    check(shed["completed"] == "2026-05-02", "close-out date parsed")

    plans_b = {p["file"]: p for p in projects["example-lib"]["plans"]}
    check("2026-06-20-fleet-master-plan.md" not in plans_b,
          "master plan emits nothing")
    mystery = plans_b["2026-06-15-mystery-plan.md"]
    # Its stage is unknown and it is NOT in-flight — see
    # test_legacy_unmeasurable for the bucket that decision belongs to.
    check(mystery["active"] is False and mystery["stage"] is None,
          "malformed plan degrades to inactive/stage-unknown")
    check("stage unknown" in (mystery["note"] or ""),
          "malformed plan carries the degradation note, not dropped")


def test_partial_and_abandoned(tmp):
    """The `[~]` partial state and abandoned-plan suppression."""
    print("[partial + abandoned]")
    home, vault = make_env(tmp)
    out = run_scan(home)
    projects = {p["name"]: p for p in out["projects"]}
    plans_a = {p["file"]: p for p in projects["example-app"]["plans"]}

    # --- `[~]` is counted as decided, never silently dropped -----------------
    partial = plans_a["2026-07-24-partial-plan.md"]
    check((partial["done"], partial["total"]) == (1, 3),
          "partial task counts toward total, never toward done (1/3)")
    check(partial["done"] != 2,
          "partial NOT classified as done (the `!= \" \"` bug would give 2)")
    check(partial["partial"] == 1, "partial tasks reported in their own count")
    check(partial["total"] == 3,
          "partial task not dropped from total")
    check(partial["next_task"] == "Task 1.2: Wire the middle",
          "an in-flight task is the next task, not skipped over")
    check(partial["active"] is True, "a plan with partial work is still active")

    # --- a `[~]` gate check outranks a close-out line -----------------------
    # Every task is `[x]` and the plan carries **Completed:**, so reading tasks
    # alone would retire it. It is not finished: a gate check could not be run,
    # which is the one thing a task marker cannot say.
    blocked = plans_a.get("2026-07-25-blocked-plan.md")
    check(blocked is not None, "the blocked-gate plan is listed at all")
    if blocked:
        check(blocked.get("blocked_gate") is True,
              f"a `[~]` gate check is reported ({blocked.get('blocked_gate')!r})")
        check(blocked["active"] is True,
              "a plan whose gate could not be run is STILL ACTIVE — all tasks "
              "done plus a close-out line must not retire it")
        check(blocked.get("note") and "gate" in blocked["note"].lower(),
              f"and the note says why ({blocked.get('note')!r})")

    # --- the author's answer-back retires the plan again --------------------
    acc = plans_a.get("2026-07-26-accepted-plan.md")
    check(acc is not None, "the accepted plan is listed")
    if acc:
        check(acc["active"] is False,
              "a `**Blocked-accepted:**` plan is retired — the author looked, "
              "understood, and closed it, and the tool stops arguing")
        check(acc.get("blocked_gate") is False,
              f"and it no longer reports as blocked ({acc.get('blocked_gate')!r})")

    # --- abandoned: suppressed from recommendation, NOT hidden --------------
    ghost = plans_a["2026-07-24-ghost-plan.md"]
    check(ghost["abandoned"] is True, "**Abandoned:** marker parsed")
    check(ghost["abandoned_reason"] == "2026-07-22 — superseded by the widget pipeline",
          f"the marker's reason reaches the scan JSON — the skill lists a "
          f"suppressed plan WITH its reason, so the boolean alone is not enough "
          f"({ghost.get('abandoned_reason')!r})")
    check(plans_a["2026-07-24-rumor-plan.md"]["abandoned_reason"] is None,
          "a banner-only plan carries no abandonment reason")
    check(ghost["active"] is False,
          "abandoned plan is not rankable as available work")
    check("2026-07-24-ghost-plan.md" in plans_a,
          "abandoned plan still LISTED — suppressed from recommendation, "
          "not hidden from the board")
    check(ghost["total"] == 1 and ghost["next_task"] == "Task 1.1: Summon the ghost",
          "abandoned plan's tasks stay parsed and visible")

    # --- banner prose is advisory only, never suppressing --------------------
    rumor = plans_a["2026-07-24-rumor-plan.md"]
    check(rumor["abandoned"] is False,
          "prose banner alone never marks a plan abandoned")
    check(rumor["active"] is True,
          "prose banner never suppresses — a false positive would hide live work")
    check("not suppressed" in (rumor["note"] or ""),
          "banner carries a non-suppressing advisory nudging the real marker")

    # --- notes accumulate; a later note never silently wins ------------------
    # Banner prose + a stale **Completed:** + an open task are all true at once.
    # A stale-close-out warning that overwrote the banner advisory would drop
    # the nudge exactly where it is most needed.
    haunted = plans_a["2026-07-24-haunted-plan.md"]
    check("not suppressed" in (haunted["note"] or ""),
          "banner advisory survives alongside a stale-close-out note")
    check("completed marker present" in (haunted["note"] or ""),
          "stale-close-out note still reported")
    check(haunted["abandoned"] is False and haunted["active"] is True,
          "banner + stale Completed still never suppresses")

    # --- the live plans are untouched by either mechanism -------------------
    widget = plans_a["2026-06-01-widget-plan.md"]
    check(widget["abandoned"] is False and widget["note"] is None,
          "an ordinary live plan is neither abandoned nor advised")


def test_signals(tmp):
    print("[signals]")
    home, vault = make_env(tmp)
    out = run_scan(home)
    projects = {p["name"]: p for p in out["projects"]}
    app, lib = projects["example-app"], projects["example-lib"]

    expected_age = (datetime.now(tz=timezone.utc).date() - date(2026, 1, 1)).days
    check(app["git"]["last_commit"] == "2026-01-01"
          and app["git"]["age_days"] == expected_age,
          "git recency: fixed-date commit yields exact age_days")
    check(lib["git"] is None
          and any(e.startswith("git:") for e in lib["errors"]),
          "non-git repo degrades to git:null + errors entry, project kept")

    bl = app["backlog"]
    check(bl["open"] == 3, "backlog open count")
    check(bl["parked"] == 1
          and bl["parked_items"][0]["title"] == "Paint the trim"
          and "dry season" in bl["parked_items"][0]["note"],
          "parked: annotation parsed with reason")

    mat = app["maturity"]
    check(mat["axes"]["Documentation"] == {"done": 1, "open": 1, "na": 0},
          "maturity axis Documentation 1 done / 1 open")
    check(mat["axes"]["Testing & CI"] == {"done": 1, "open": 0, "na": 1},
          "maturity axis Testing & CI counts [N/A]")
    check(lib["maturity"] is None, "missing MATURITY.md yields null, no error")

    check(app["dependents"] == [{"project": "example-lib",
                                 "why": "example-lib consumes example-app's widget API"}],
          "integration out-edge: example-lib depends on example-app")
    check(app["depends_on"][0]["project"] == "example-upstream",
          "integration in-edge: example-app depends on example-upstream")


def test_decisions(tmp):
    """The decisions collector: summary, absent register, corrupt register."""
    print("[decisions]")
    home, vault = make_env(tmp)
    before = tree_digest(vault)
    out = run_scan(home)
    projects = {p["name"]: p for p in out["projects"]}

    dec = projects["example-app"][DECISIONS_KEY]
    check(set(dec) == {"count", "malformed", "domains", "last_decided"},
          "decisions block shape is {count, malformed, domains, last_decided}")
    check(dec["count"] == 2,
          "only well-formed entries counted (the plain-hyphen heading is excluded)")
    check(dec["domains"] == ["rust", "ubuntu"],
          "domains lowercased, deduped and sorted, with `none` dropped")
    check(dec["last_decided"] == "2026-07-10",
          "last_decided is the newest Decided date among well-formed entries — "
          "the malformed entry's later 2026-09-09 must not win")
    check(dec["malformed"] == 1,
          "a register with SOME bad entries must still report them — compass has to "
          "see the same cleanup signal the decisions roll-up shows, not just count them out")
    check(not any(e.startswith("decisions:") for e in projects["example-app"]["errors"]),
          "an entry-level defect is a `malformed` count, not a register-level error")

    check(projects["example-lib"][DECISIONS_KEY] is None,
          "project with no decisions.md emits null (the fallback), never a crash")

    check("example-broken" in projects,
          "corrupt register never drops the project from the scan")
    check(projects["example-broken"][DECISIONS_KEY] == {"count": 0, "malformed": 0,
                                                      "domains": [], "last_decided": None},
          "corrupt register degrades to an empty summary")
    check(any(e.startswith("decisions:") for e in projects["example-broken"]["errors"]),
          "corrupt register lands a message in that project's errors[]")

    check(tree_digest(vault) == before,
          "decisions collector writes nothing under the vault (read-only)")


def test_legacy_unmeasurable(tmp):
    """A plan nobody can measure is not in-flight work.

    A plan with zero parseable `Status:` fields and no close-out line, left
    `active`, would be reported as in-flight work at an unknown stage — a count
    nobody could act on and nobody could check. It is its own bucket: still
    emitted, still carrying its note, never counted as active.
    """
    print("[legacy/unmeasurable]")
    home, vault = make_env(tmp)
    out = run_scan(home)
    projects = {p["name"]: p for p in out["projects"]}
    plans_b = {p["file"]: p for p in projects["example-lib"]["plans"]}

    mystery = plans_b["2026-06-15-mystery-plan.md"]
    check(mystery.get("unmeasurable") is True,
          f"a zero-Status plan with no close-out line is bucketed "
          f"legacy/unmeasurable ({mystery.get('unmeasurable')!r})")
    check(mystery["active"] is False,
          "and is NOT part of the active in-flight population")
    check(mystery["completed"] is None and mystery["abandoned"] is False,
          "unmeasurability alone puts it there — no close-out line and no "
          "abandonment marker are doing the work in this fixture")

    # degrade loudly: the plan is quieter, never absent.
    check("2026-06-15-mystery-plan.md" in plans_b,
          "the unmeasurable plan is still emitted, not filtered out of the scan")
    check("stage unknown" in (mystery["note"] or "")
          and "legacy" in (mystery["note"] or "").lower(),
          f"its note still says why it cannot be measured, and names the bucket "
          f"({mystery.get('note')!r})")
    check(sum(1 for p in projects["example-lib"]["plans"] if p["active"]) == 0,
          "example-lib's only non-master plan is unmeasurable, so it contributes "
          "zero to the in-flight count rather than one unknown-stage plan")

    # --- the other half: a measurable plan is untouched ---------------------
    plans_a = {p["file"]: p for p in projects["example-app"]["plans"]}
    widget = plans_a["2026-06-01-widget-plan.md"]
    check(widget["active"] is True and widget.get("unmeasurable") is False,
          "a plan with parseable open tasks still classifies active, and is "
          "not in the bucket")
    check(widget["stage"] == 2
          and widget["next_task"] == "Task 2.2: Install windows",
          "and its stage / next task are unchanged by the new bucket")
    check(all(p.get("unmeasurable") is False for p in plans_a.values()),
          "no example-app plan — every one carries parseable Status fields — "
          "is bucketed, so the filter keys on measurability and nothing else")

    # A retired plan is inactive for its OWN reason; the bucket must not be
    # read backwards as "every inactive plan is unmeasurable".
    shed = plans_a["2026-05-01-shed-plan.md"]
    check(shed["active"] is False and shed.get("unmeasurable") is False,
          "a closed-out plan is inactive without being unmeasurable")


def test_business(tmp):
    """The business layer comes from the configured scanner and nowhere else."""
    print("[business]")
    home, vault = make_env(tmp)
    out = run_scan(home)
    check(all("business" not in p for p in out["projects"]),
          "no scanner configured: no project carries a business block")

    scanner = tmp / "business-scan.py"
    scanner.write_text(
        "import json\n"
        "print(json.dumps({'projects': [\n"
        "  {'name': 'example-app', 'assessed': True, 'verdict': 'go',\n"
        "   'monetization': {'model': 'subscription'}, 'gtm': {'pct': 40},\n"
        "   'last_reviewed_age_days': 3},\n"
        "  {'name': 'pair', 'group': True, 'assessed': True, 'verdict': 'hold',\n"
        "   'members': ['apps/example-lib']}]}))\n")
    out = run_scan(home, BUSINESS_SCAN_PATH=scanner)
    projects = {p["name"]: p for p in out["projects"]}
    biz = projects["example-app"].get("business") or {}
    check(biz.get("verdict") == "go" and biz.get("model") == "subscription"
          and biz.get("stage") == "launched",
          f"BUSINESS_SCAN_PATH scanner output reaches the project ({biz!r})")
    lib_biz = projects["example-lib"].get("business") or {}
    check(lib_biz.get("group") == "pair" and lib_biz.get("verdict") == "hold",
          f"a group's state lands on its qualified member ({lib_biz!r})")

    # The config.json argv form: the same scanner named by the obsidian-wiki config.
    cfg = home / ".config" / "obsidian-wiki" / "config.json"
    doc = json.loads(cfg.read_text())
    doc["business_scan"] = [sys.executable, "-I", str(scanner)]
    cfg.write_text(json.dumps(doc))
    out = run_scan(home)
    projects = {p["name"]: p for p in out["projects"]}
    check((projects["example-app"].get("business") or {}).get("verdict") == "go",
          "config.json business_scan argv is run too")

    broken = tmp / "broken-scan.py"
    broken.write_text("import sys\nprint('not json')\nsys.exit(0)\n")
    out = run_scan(home, BUSINESS_SCAN_PATH=broken)
    check(all("business" not in p for p in out["projects"])
          and len(out["projects"]) == 3,
          "a broken scanner degrades to no business layer, never a failed scan")


OPEN_PLAN = ("# Project Plan: {t}\n\n## Stage 1: S\n\n### Task 1.1: {t} first task\n"
             "- **Status:** [ ]\n")


def test_plan_enumeration(tmp):
    """compass reads the same plan files plan-status-audit and unify read.

    The vault's plans/ holds nested plan sets (`plans/<set>/01-….md`) and plans
    whose names do not end in `-plan.md`; a reader that sees only top-level
    `*-plan.md` files reports less in flight than the vault holds, while the other
    two readers report it. Backups and non-plan documents stay out.
    """
    print("[plan enumeration]")
    home, vault = make_env(tmp)
    plans = vault / "Portfolio" / "apps" / "example-lib" / "plans"
    (plans / "2026-08-01-phase-set").mkdir()
    (plans / "2026-08-01-phase-set" / "01-phase-one.md").write_text(OPEN_PLAN.format(t="nested"))
    (plans / "2026-08-02-migration.md").write_text(OPEN_PLAN.format(t="unsuffixed"))
    (plans / "2026-08-03-widget-design.md").write_text("# Design: widget\n\n- [ ] an idea\n")
    (plans / "README.md").write_text(OPEN_PLAN.format(t="readme"))
    (plans / "backlog.md").write_text(OPEN_PLAN.format(t="stray backlog"))
    backup = plans / ".audit-backups" / "20260801-120000"
    backup.mkdir(parents=True)
    (backup / "2026-08-02-migration.md").write_text(OPEN_PLAN.format(t="backup copy"))

    out = run_scan(home)
    lib = {p["name"]: p for p in out["projects"]}["example-lib"]
    files = {p["file"]: p for p in lib["plans"]}
    nested = files.get("2026-08-01-phase-set/01-phase-one.md")
    check(nested is not None, f"a nested plan reaches compass, named by its path under "
                              f"plans/ ({sorted(files)})")
    if nested:
        check(nested["active"] is True and nested["next_task"] == "Task 1.1: nested first task",
              "...and is read like any other plan")
    check("2026-08-02-migration.md" in files,
          "a plan whose name does not end in -plan.md reaches compass")
    check(not any(".audit-backups" in f for f in files),
          "a plan-status backup copy is not a plan")
    check("2026-08-03-widget-design.md" not in files,
          "a design document is not a plan (the parser's is_not_a_plan)")
    check("README.md" not in files and "backlog.md" not in files,
          f"a README.md or backlog.md in plans/ is not a plan, as unify excludes them "
          f"({sorted(files)})")

    psa_path = SCRIPT.resolve().parents[2] / "portfolio" / "scripts" / "plan-status-audit.py"
    spec = importlib.util.spec_from_file_location("psa_for_compass_test", psa_path)
    psa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(psa)
    rows = psa.enumerate_plans(vault, [{"name": "example-lib", "area": "apps", "path": "x"}])
    audited = {f.relative_to(plans).as_posix() for (p, d, fs, _n) in rows
               if p["name"] == "example-lib" for f in fs
               if not psa.pr.not_a_plan(f)
               and not psa.pp.is_master_plan(f.read_text(), f)}
    check(set(files) == audited,
          f"compass lists exactly the plans plan-status-audit enumerates "
          f"(compass-only: {sorted(set(files) - audited)}, "
          f"audit-only: {sorted(audited - set(files))})")


def main():
    for test in (test_envelope_and_refusals, test_plan_state, test_partial_and_abandoned,
                 test_signals, test_decisions, test_legacy_unmeasurable, test_business,
                 test_plan_enumeration):
        with tempfile.TemporaryDirectory() as td:
            try:
                test(Path(td))
            except Exception as e:  # a crashed case is a failure, never a skip
                check(False, f"{test.__name__} raised {type(e).__name__}: {e}")
    if FAILURES:
        print(f"\nFAILED — {len(FAILURES)} check(s):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("\nOK — all compass-scan fixture checks passed")


if __name__ == "__main__":
    main()
