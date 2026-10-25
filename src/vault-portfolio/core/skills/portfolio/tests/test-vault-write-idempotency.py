#!/usr/bin/env python3
"""Every vault-writing `portfolio-*.py` leaves an unchanged vault untouched.

The vault is not under version control, and it is often synced or network-backed.
A write that changes nothing is therefore not free: it churns the sync layer, can
manufacture conflict copies, and destroys the "nothing moved" signal an operator
reads off mtimes. The contract: re-running with no upstream change produces zero
writes.

The roll-ups embed `**Last rebuilt:** {TODAY}`, so a same-day double run cannot
tell a guarded write from an unguarded one — both see the same date. These cases
change the date between the runs, because a same-date probe passes against the bug.

The claim is class-wide, so this file also pins the three scripts that legitimately
do NOT route through `write_if_changed`:

  * `portfolio-unify.py` APPENDS to a curated register — a changed-check on
    `existing + new` would compare a strictly longer string and always fire.
    Its guard sits one level up, in the dedup that leaves nothing to append.
  * `portfolio-migrate.py` performs a ONE-TIME move, guarded structurally by
    two independent refusals — an emptied repo docs/ has nothing to migrate, and
    a populated vault home is refused — and its two in-place rewriters carry
    their own equality checks. Both are exercised below, the second only because
    docs/ is deliberately repopulated: it sits behind the first.
  * `portfolio-scan.py` writes no vault file at all: its only writes are single
    registry entries, appended or removed. Its guard is the drift itself — a found
    root already registered is not a candidate, so a re-run has nothing to add.

Each of those is a justification only because the case below proves it. The
migrate dry run over the synthetic fixture repos is compared with
`migrate-dryrun.txt`.

Throwaway HOME and temp vaults only; fake_env() refuses to run if the resolved
vault escapes the temp tree. Stdlib + PyYAML, no pytest. Run:
  python3 -I src/vault-portfolio/core/skills/portfolio/tests/test-vault-write-idempotency.py
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
FIXTURES = HERE / "fixtures"
DRYRUN = HERE / "migrate-dryrun.txt"

for _k in list(os.environ):
    if _k.startswith(("OBSIDIAN_", "BUSINESS_", "VAULT_CONTEXT_")):
        os.environ.pop(_k)
os.environ["HOME"] = tempfile.mkdtemp(prefix="idem-home-")

FAILURES: list[str] = []
BL = "BL"     # spelled apart so this file carries no literal register id


def check(ok, msg):
    print(f"  {'ok' if ok else 'FAIL'}: {msg}")
    if not ok:
        FAILURES.append(msg)


def load(name):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pi = load("portfolio-integrate")
pu = load("portfolio-unify")
pm = load("portfolio-migrate")
ps = load("portfolio-scan")


def expand_ids(root: Path):
    for p in root.rglob("*.md"):
        t = p.read_text(encoding="utf-8")
        p.write_text(t.replace("{DEC}", "DEC").replace("{GDEC}", "GDEC").replace("{BL}", "BL"),
                     encoding="utf-8")


# A distinctive frozen mtime, far from "now", so "this file was rewritten" is a
# positive observation rather than an inference from clock resolution: any write
# — even one producing identical bytes — moves it to the present.
MARK = 1_000_000_000_000_000_000


def freeze(*paths):
    for p in paths:
        os.utime(p, ns=(MARK, MARK))


def untouched(p: Path) -> bool:
    return p.stat().st_mtime_ns == MARK


@contextmanager
def fake_env(mod, vault: Path, registry: Path, argv):
    """Point the config at a throwaway tree (HOME + config.json) and set argv.

    Asserted rather than trusted: a test that silently ran against a real vault
    would be a destructive bug wearing a green tick.
    """
    home = vault.parent / f"{mod.__name__}-home"
    cfg = home / ".config" / "obsidian-wiki" / "config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"default_vault": str(vault), "registry": str(registry)}))
    old = (os.environ["HOME"], sys.argv)
    os.environ["HOME"], sys.argv = str(home), list(argv)
    try:
        resolved = mod.pr.vault_dir()
        assert resolved == vault, f"vault_dir() escaped the fixture: {resolved}"
        yield
    finally:
        os.environ["HOME"], sys.argv = old


def run_main(mod, vault, registry, argv):
    """(stdout, stderr, exit code) of one main() run. The code is main()'s return
    value, or a SystemExit's: 0 for None, 1 for a message, else the number."""
    out, err = io.StringIO(), io.StringIO()
    with fake_env(mod, vault, registry, argv):
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = mod.main()
            except SystemExit as e:
                code = e.code
    if code is None:
        code = 0
    elif not isinstance(code, int):
        print(code, file=err)
        code = 1
    return out.getvalue(), err.getvalue(), code


def write_registry(path: Path, projects) -> Path:
    path.write_text(yaml.safe_dump({"projects": projects}))
    return path


def integration_md(project, depends=(), impacts=()):
    fm = {"project": project}
    if depends:
        fm["depends_on"] = [{"target": f"[[{t}]]", "why": w} for t, w in depends]
    if impacts:
        fm["impacts"] = [{"target": f"[[{t}]]", "why": w} for t, w in impacts]
    return f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n\n# integration\n"


# --------------------------------------------------------------------------
def generated_stamp_case():
    """`write_if_changed` treats a bare `Generated:` line-2 stamp as a timestamp.

    One roll-up (global-business.md) is rendered by an external scanner that stamps
    `Generated:` instead of `**Last rebuilt:**`. Normalising only the first form
    would leave that roll-up rewriting itself on every date change.
    """
    pr = load("portfolio-rebuild")
    with tempfile.TemporaryDirectory() as root:
        f = Path(root) / "global-business.md"
        day1 = "# Global Business\nGenerated: 2026-01-01\n\nbody unchanged\n"
        day2 = "# Global Business\nGenerated: 2026-06-30\n\nbody unchanged\n"
        f.write_text(day1)
        freeze(f)
        pr.write_if_changed(f, day2)
        check(untouched(f) and f.read_text() == day1,
              "a `Generated:` stamp change alone rewrites nothing")

        changed = "# Global Business\nGenerated: 2026-06-30\n\nbody CHANGED\n"
        pr.write_if_changed(f, changed)
        check(f.read_text() == changed,
              "and a real content change still writes — the normalisation must not "
              "swallow the diff it exists to detect")

        # count=1 is load-bearing: a `Generated:` in the content further down is
        # content, not a header stamp, and must still register as a change.
        f.write_text("# G\nGenerated: 2026-01-01\n\nrow\nGenerated: 2026-01-01\n")
        pr.write_if_changed(f, "# G\nGenerated: 2026-06-30\n\nrow\nGenerated: 2026-06-30\n")
        check("row\nGenerated: 2026-06-30" in f.read_text(),
              "a second `Generated:` in the body is content, not a stamp")


def io_vs_decode_case():
    """An I/O failure and a decode failure are different facts with different answers.

    A file that could not be read tells us nothing about what is in it, and on a
    network-backed vault a transient I/O fault is the likely cause; overwriting it
    is a guess dressed as a repair. Undecodable bytes in a fully regenerable roll-up
    are a different case and may be regenerated.
    """
    pr = load("portfolio-rebuild")
    with tempfile.TemporaryDirectory() as root:
        rootp = Path(root)

        bad = rootp / "bad.md"
        bad.write_bytes(b"# roll-up\n\xff\xfe not utf-8\n")
        text, why = pr.read_utf8(bad)
        check(text is None and why == "decode",
              f"invalid UTF-8 is reported as a DECODE failure (got {why!r})")

        unreadable = rootp / "adir"
        unreadable.mkdir()
        text, why = pr.read_utf8(unreadable)
        check(text is None and why == "io",
              f"an unreadable path is reported as an I/O failure, not a decode one "
              f"(got {why!r})")

        wrote = pr.write_if_changed(unreadable, "replacement content")
        check(wrote is False and unreadable.is_dir(),
              "write_if_changed REFUSES on an I/O failure")

        wrote = pr.write_if_changed(bad, "# roll-up\n\nregenerated\n")
        check(wrote is True and bad.read_text() == "# roll-up\n\nregenerated\n",
              "a DECODE failure still regenerates — narrowing the I/O case must not "
              "narrow this one too")


def atomic_write_case():
    """A crash mid-write leaves the old file, not half a new one."""
    pr = load("portfolio-rebuild")
    with tempfile.TemporaryDirectory() as root:
        target = Path(root) / "global-backlog.md"
        target.write_text("original content\n")

        class Boom(Exception):
            pass

        real_replace = os.replace

        def exploding_replace(*a, **k):
            raise Boom("interrupted between write and rename")

        os.replace = exploding_replace
        try:
            try:
                # Through write_if_changed, NOT atomic_write directly, so the case
                # also pins that the caller uses the atomic helper.
                pr.write_if_changed(target, "new content that never lands\n")
            except Boom:
                pass
        finally:
            os.replace = real_replace

        check(target.read_text() == "original content\n",
              "an interruption before the rename leaves the ORIGINAL intact")
        leftovers = [f.name for f in Path(root).iterdir() if f.name != "global-backlog.md"]
        check(leftovers == [], f"and no temp file is left beside it ({leftovers})")

        pr.atomic_write(target, "new content\n")
        check(target.read_text() == "new content\n", "the normal path still writes")


def atomic_write_mode_case():
    """The rename must not change who can read a roll-up.

    The temp file is created private (0600), and `os.replace` puts that new inode
    where the old file was. Without a chmod, every roll-up ends up 0600, whatever
    mode the file had and whatever the umask says a new file should get.
    """
    pr = load("portfolio-rebuild")
    old_umask = os.umask(0o022)
    try:
        with tempfile.TemporaryDirectory() as root:
            kept = Path(root) / "global-backlog.md"
            kept.write_text("original\n")
            os.chmod(kept, 0o640)
            pr.atomic_write(kept, "replaced\n")
            mode = kept.stat().st_mode & 0o777
            check(mode == 0o640, f"a replaced file keeps its mode (0640, got {mode:04o})")

            fresh = Path(root) / "global-maturity.md"
            pr.atomic_write(fresh, "new\n")
            mode = fresh.stat().st_mode & 0o777
            check(mode == 0o644,
                  f"a new file gets the umask default under umask 022 (0644, got {mode:04o})")
        os.umask(0o077)
        with tempfile.TemporaryDirectory() as root:
            private = Path(root) / "global-decisions.md"
            pr.atomic_write(private, "new\n")
            mode = private.stat().st_mode & 0o777
            check(mode == 0o600,
                  f"a new file under umask 077 is 0600, as the umask says (got {mode:04o})")
    finally:
        os.umask(old_umask)


def vault_vanishes_mid_run_case():
    """The vault disappearing AFTER the check must not be rebuilt from nothing.

    The reachability check runs once in main(); the writes follow it, and every
    `mkdir(parents=True)` downstream would happily build the chain again.
    """
    pr = load("portfolio-rebuild")
    with tempfile.TemporaryDirectory() as root:
        rootp = Path(root)
        vault = rootp / "vault"
        (vault / "Portfolio").mkdir(parents=True)
        check(pr.vault_live(vault), "a mounted vault is live")

        shutil.rmtree(vault)
        check(not pr.vault_live(vault), "a vault whose root is gone is NOT live")

        vault.mkdir()
        check(not pr.vault_live(vault),
              "an existing root with no Portfolio/ is not live either — that is what "
              "an UNMOUNTED mountpoint looks like")

        repo = rootp / "repo"
        (repo / "docs" / "plans").mkdir(parents=True)
        (repo / "docs" / "plans" / "p.md").write_text("# plan\n")
        shutil.rmtree(vault)

        status, label, msg = pm.migrate_project(
            {"path": str(repo), "area": "apps", "name": "example-app"}, vault, True)
        check(status == "fail",
              f"migrate_project REFUSES when the vault went away after the check "
              f"(got {status!r}: {msg})")
        check(not vault.exists(), "and the vault tree is NOT recreated")
        check((repo / "docs" / "plans" / "p.md").exists(),
              "the repo's only copy of its docs is still in the repo")


def integrate_cases():
    """Two `integrate --write` runs on an unchanged vault, on different days."""
    with tempfile.TemporaryDirectory() as root:
        rootp = Path(root)
        vault = rootp / "vault"
        app = vault / "Portfolio" / "apps" / "example-app"
        cli = vault / "Portfolio" / "apps" / "example-cli"
        app.mkdir(parents=True)
        cli.mkdir(parents=True)
        (app / "integration.md").write_text(
            integration_md("example-app", impacts=[("example-cli", "the app's format binds the cli")]))
        (cli / "integration.md").write_text(
            integration_md("example-cli", depends=[("example-app", "reads the app's format")]))
        (app / "backlog.md").write_text(
            f"# Backlog\n\n## {BL}-001 — teach the cli the new format\n\n"
            "- **Tags:** integration, edge=app-format\n\n---\n")
        reg = write_registry(rootp / "registry.yaml", [
            {"path": str(rootp / "repo-app"), "name": "example-app", "area": "apps"},
            {"path": str(rootp / "repo-cli"), "name": "example-cli", "area": "apps"},
        ])

        graph = vault / "Portfolio" / "integration-graph.md"
        ibl = vault / "Portfolio" / "integration-backlog.md"

        old_today = pi.TODAY
        try:
            pi.TODAY = "2026-01-01"
            _o, err, rc = run_main(pi, vault, reg, ["portfolio-integrate.py", "--write"])
            check(rc == 0 and graph.exists() and ibl.exists(),
                  f"the first --write creates both roll-ups (rc={rc}: {err.strip()[:160]})")
            first_graph, first_ibl = graph.read_text(), ibl.read_text()
            check("**Last rebuilt:** 2026-01-01" in first_graph,
                  "...stamped with the simulated date, so the date IS the variable")

            # TODAY is bound at import, so rebinding the module global is what makes
            # this a different DAY rather than a repeat of run 1.
            freeze(graph, ibl)
            pi.TODAY = "2026-06-15"
            out, _, rc = run_main(pi, vault, reg, ["portfolio-integrate.py", "--write"])
            check(rc == 0 and graph.read_text() == first_graph and ibl.read_text() == first_ibl,
                  "a second run on a LATER date leaves both roll-ups byte-identical")
            check(untouched(graph) and untouched(ibl),
                  "...and does not write them at all (frozen mtimes survive)")
            check("unchanged" in out and "integration-graph.md" in out,
                  "...and the run reports the files as unchanged rather than 'wrote'")

            # Teeth: edit the depends_on reason (the graph renders depends_on
            # edges, so an impacts-only edit would change nothing).
            (cli / "integration.md").write_text(
                integration_md("example-cli", depends=[("example-app", "reads the app's format v2")]))
            freeze(graph, ibl)
            _o, _e, rc = run_main(pi, vault, reg, ["portfolio-integrate.py", "--write"])
            check(rc == 0 and not untouched(graph), "a real upstream edit DOES rewrite the graph")
            check("reads the app's format v2" in graph.read_text(),
                  "...with the new edge reason, so the rewrite carried the change")
            check(untouched(ibl), "...while the untouched roll-up stays untouched")
        finally:
            pi.TODAY = old_today


# --------------------------------------------------------------------------
LEGACY_PLAN = ("# Project Plan: legacy\n\n## Stage 1: S\n\n### Task 1.1: T\n"
               "- [ ] an unresolved legacy item\n")
STATUS_PLAN = ("# Project Plan: status\n\n## Stage 1: S\n\n### Task 1.1: one\n"
               "- **Status:** [x]\n\n### Task 1.2: two\n- **Status:** [~]\n")


def unify_cases():
    """The justified exception: an append whose guard is the dedup, not a diff."""
    with tempfile.TemporaryDirectory() as root:
        rootp = Path(root)
        vault = rootp / "vault"
        repo = rootp / "repo"
        repo.mkdir()
        home = vault / "Portfolio" / "apps" / "example-app"
        (home / "plans").mkdir(parents=True)
        (home / "plans" / "2026-01-01-legacy-plan.md").write_text(LEGACY_PLAN)
        reg = write_registry(rootp / "registry.yaml", [
            {"path": str(repo), "name": "example-app", "area": "apps"}])
        backlog = home / "backlog.md"

        old_today = pu.TODAY
        try:
            pu.TODAY = "2026-01-01"
            _o, _e, rc = run_main(pu, vault, reg, ["portfolio-unify.py", "--write"])
            check(rc == 0 and backlog.exists() and f"{BL}-001" in backlog.read_text(),
                  "unify's first --write appends candidates to the backlog")
            first = backlog.read_text()

            # render_entry() stamps TODAY into every entry, so a naive re-render on
            # a later date would differ. Dedup keys on **Source:**, so there is
            # nothing new to append and the file is not opened.
            freeze(backlog)
            pu.TODAY = "2026-06-15"
            out, err, rc = run_main(pu, vault, reg, ["portfolio-unify.py", "--write"])
            check(rc == 0 and "WRITE: 0 new entries, 1 duplicates skipped" in out,
                  f"the second unify ran over the plan: exit 0, and its summary finds the "
                  f"candidate already registered (rc={rc}: {out.strip()[-160:]} "
                  f"{err.strip()[:160]})")
            check(backlog.read_text() == first,
                  "a second unify on a LATER date leaves backlog.md byte-identical")
            check(untouched(backlog), "...and does not write it at all, despite TODAY moving")
            check("2026-06-15" not in first, "...so no entry carries the second run's date")

            # Teeth: a genuinely new candidate must still be appended.
            (home / "plans" / "2026-01-24-status-plan.md").write_text(STATUS_PLAN)
            freeze(backlog)
            _o, _e, rc = run_main(pu, vault, reg, ["portfolio-unify.py", "--write"])
            check(rc == 0 and not untouched(backlog) and len(backlog.read_text()) > len(first),
                  "a new plan DOES append — the no-write above is a guard, not inertia")
            check(backlog.read_text().startswith(first),
                  "...purely by append: the previously curated bytes are carried through")
        finally:
            pu.TODAY = old_today


# --------------------------------------------------------------------------
def migrate_cases():
    """The other justified exception: a one-time move plus two equality-guarded
    in-place rewriters."""
    with tempfile.TemporaryDirectory() as root:
        rootp = Path(root)
        vault = rootp / "vault"
        repo = rootp / "repo"
        (repo / "docs" / "plans").mkdir(parents=True)
        (repo / "docs" / "plans" / "2026-05-01-a-plan.md").write_text("# Plan\n")
        (repo / "docs" / "backlog.md").write_text("# Backlog\n")
        (repo / "docs" / "MATURITY.md").write_text("# Maturity\n\n- [x] auto:docs/README.md\n")
        (vault / "Portfolio").mkdir(parents=True)
        proj = {"path": str(repo), "name": "example-app", "area": "apps"}
        home = vault / "Portfolio" / "apps" / "example-app"

        status, _, _ = pm.migrate_project(proj, vault, True)
        check(status == "ok", "migrate's first --write moves the docs into the vault")
        moved = sorted(p for p in home.rglob("*") if p.is_file())
        check(len(moved) == 3, f"...all three files landed ({len(moved)})")
        before = {p: p.read_bytes() for p in moved}

        freeze(*moved)
        status2, _, why2 = pm.migrate_project(proj, vault, True)
        check(status2 == "skip", "a second migrate is refused structurally, not re-run")
        check("nothing to migrate" in why2,
              "...by the emptied-docs guard — WHICH guard fired, not merely that one did")
        check(all(p.read_bytes() == before[p] for p in moved)
              and all(untouched(p) for p in moved),
              "...and touches nothing already in the vault")

        # The populated-home preflight sits BEHIND the emptied-docs guard, so a plain
        # re-run never reaches it. Repopulating docs/ puts it in front.
        (repo / "docs" / "plans").mkdir(parents=True, exist_ok=True)
        (repo / "docs" / "plans" / "2026-05-02-b-plan.md").write_text("# Plan B\n")
        freeze(*moved)
        status3, _, why3 = pm.migrate_project(proj, vault, True)
        check(status3 == "skip" and "already populated" in why3,
              "a populated vault home refuses even when docs/ has new files to move")
        check(all(untouched(p) for p in moved), "...without touching what is already there")
        shutil.rmtree(repo / "docs" / "plans")

        sidecar = repo / ".claude" / "vault-context.md"
        check(sidecar.exists(), "the sidecar was created by the first migrate")
        freeze(sidecar)
        pm.write_sidecar_home(repo, home)
        check(untouched(sidecar), "write_sidecar_home is a no-op when the home is unchanged")
        pm.write_sidecar_home(repo, vault / "Portfolio" / "apps" / "moved")
        check(not untouched(sidecar),
              "...and DOES write when the home changes — the guard is not inertia")

        mat = home / "MATURITY.md"
        check("auto:repo:docs/README.md" in mat.read_text(),
              "the evidence rewrite ran on the migrated MATURITY.md")
        freeze(mat)
        pm.rewrite_maturity_evidence(mat)
        check(untouched(mat), "rewrite_maturity_evidence is a no-op once every line is prefixed")
        mat.write_text("# Maturity\n\n- [x] auto:docs/CHANGELOG.md\n")
        freeze(mat)
        pm.rewrite_maturity_evidence(mat)
        check(not untouched(mat) and "auto:repo:docs/CHANGELOG.md" in mat.read_text(),
              "...and DOES rewrite an unprefixed line — the guard is not inertia")

        # A line that already names its tree keeps it. `portfolio:` evidence lives in
        # the vault home, so prefixing it with `repo:` would point a reader at a repo
        # file that does not exist.
        scoped = ("- [x] auto:portfolio:security/reports/audit-20260101-1200.md\n"
                  "- [x] auto:repo:docs/README.md\n")
        mat.write_text("# Maturity\n\n" + scoped)
        freeze(mat)
        pm.rewrite_maturity_evidence(mat)
        check(untouched(mat) and mat.read_text() == "# Maturity\n\n" + scoped,
              "an already-scoped line is left alone — `portfolio:` as well as `repo:`")
        check("auto:repo:portfolio:" not in mat.read_text(),
              "...so `portfolio:` evidence is never rewritten into a repo path")
        mat.write_text("# Maturity\n\n" + scoped + "- [x] auto:docs/NEWS.md\n")
        pm.rewrite_maturity_evidence(mat)
        check(mat.read_text() == "# Maturity\n\n" + scoped + "- [x] auto:repo:docs/NEWS.md\n",
              "in a mixed file only the unscoped line gains `repo:`")


def scan_cases():
    """The third justified exception: registry edits, never a vault write."""
    with tempfile.TemporaryDirectory() as root:
        rootp = Path(root)
        vault = rootp / "vault"
        (vault / "Portfolio").mkdir(parents=True)
        dev = rootp / "dev"
        app = dev / "apps" / "example-app"
        (app / ".git").mkdir(parents=True)
        (app / "docs" / "plans").mkdir(parents=True)
        reg = rootp / "registry.yaml"
        argv = ["portfolio-scan.py", "--root", str(dev), "--add-all", "--write"]

        def vault_state():
            return sorted((p.relative_to(vault).as_posix(), p.read_bytes() if p.is_file() else b"")
                          for p in vault.rglob("*"))

        before = vault_state()
        out, err, rc = run_main(ps, vault, reg, argv)
        check(rc == 0 and reg.exists() and str(app) in reg.read_text()
              and f"added {app}" in out,
              f"scan's first --add-all --write creates the registry with the found root "
              f"(rc={rc}: {err.strip()[:160]})")
        first = reg.read_text()

        freeze(reg)
        out, err, rc = run_main(ps, vault, reg, argv)
        check(rc == 0 and "Drift — found not in registry: 0 |" in out
              and "Registry edits:" in out and "added" not in out,
              f"the second scan ran: exit 0, its drift line reports nothing found, and it "
              f"made no edit (rc={rc}: {out.strip()[-200:]} {err.strip()[:160]})")
        check(untouched(reg), "a second scan with nothing new does not write the registry")

        # Teeth: a genuinely new project root must still be appended.
        cli = dev / "apps" / "example-cli"
        (cli / ".git").mkdir(parents=True)
        (cli / "docs").mkdir()
        (cli / "docs" / "backlog.md").write_text("# Backlog\n")
        freeze(reg)
        out, err, rc = run_main(ps, vault, reg, argv)
        check(rc == 0 and not untouched(reg) and str(cli) in reg.read_text(),
              "a new project root DOES append — the no-write above is a guard, not inertia")
        check(reg.read_text().startswith(first),
              "...purely by append: the earlier registry bytes are carried through")
        check(vault_state() == before, "scan never writes under the vault")


def migrate_dryrun_case():
    """The dry run over the fixture repos writes nothing and prints migrate-dryrun.txt."""
    with tempfile.TemporaryDirectory() as root:
        rootp = Path(root)
        vault = rootp / "vault"
        (vault / "Portfolio").mkdir(parents=True)
        repos = rootp / "repos"
        names = (("proj-a-plans-and-backlog", "example-app"),
                 ("proj-b-plans-only", "example-cli"),
                 ("proj-c-bare", "example-bare"))
        projects = []
        for fixture, name in names:
            shutil.copytree(FIXTURES / fixture, repos / name)
            projects.append({"path": str(repos / name), "name": name, "area": "apps"})
        expand_ids(repos)
        reg = write_registry(rootp / "registry.yaml", projects)

        def snapshot():
            return sorted((p.relative_to(rootp).as_posix(), p.read_bytes() if p.is_file() else b"")
                          for p in rootp.rglob("*") if "-home" not in p.as_posix())

        before = snapshot()
        out, err, _ = run_main(pm, vault, reg, ["portfolio-migrate.py", "--all"])
        check(snapshot() == before, "the dry run writes nothing anywhere")
        got = out.replace(str(vault), "<vault>")
        want = DRYRUN.read_text(encoding="utf-8") if DRYRUN.exists() else ""
        check(got == want,
              f"the dry-run output matches migrate-dryrun.txt\n--- got ---\n{got}--- want ---\n{want}")


CALL_RE = re.compile(r"\bwrite_if_changed\s*\(")


def routes_through_helper(path: Path) -> bool:
    """True when the script actually CALLS write_if_changed (not just names it in prose)."""
    return any(CALL_RE.search(line) and not line.lstrip().startswith("#")
               for line in path.read_text().splitlines())


def sweep_case():
    """The class claim itself: no `portfolio-*.py` writes the vault unexamined.

    A new script that writes the vault without `write_if_changed` fails here until it
    is either routed through it or added below WITH a case in this file.
    """
    justified = {"portfolio-unify.py": unify_cases,
                 "portfolio-migrate.py": migrate_cases,
                 "portfolio-scan.py": scan_cases}
    found = sorted(p.name for p in SCRIPTS.glob("portfolio-*.py"))
    check({"portfolio-rebuild.py", "portfolio-integrate.py"} <= set(found),
          f"the sweep sees the routed writers ({found})")
    unrouted = sorted(p.name for p in SCRIPTS.glob("portfolio-*.py")
                      if not routes_through_helper(p))
    unexplained = [n for n in unrouted if n not in justified]
    check(not unexplained,
          f"every portfolio-*.py either routes through write_if_changed or is a "
          f"tested exception (unexplained: {unexplained or 'none'})")
    check(all(n in unrouted for n in justified),
          "and every listed exception is still an exception — a script that "
          "gained write_if_changed must lose its entry here, not keep a dead one")


if __name__ == "__main__":
    print("vault liveness — a mount that drops mid-run:")
    vault_vanishes_mid_run_case()
    print("read_utf8 — I/O failure is not a decode failure:")
    io_vs_decode_case()
    print("atomic_write — an interrupted write leaves the original:")
    atomic_write_case()
    print("atomic_write — the file mode survives the rename:")
    atomic_write_mode_case()
    print("write_if_changed — both stamp forms:")
    generated_stamp_case()
    print("integrate — byte-idempotent roll-ups across a date change:")
    integrate_cases()
    print("unify — justified append exception:")
    unify_cases()
    print("migrate — justified one-time-move exception:")
    migrate_cases()
    print("scan — justified registry-only exception:")
    scan_cases()
    print("migrate — the dry run over the fixture repos:")
    migrate_dryrun_case()
    print("class sweep — the exception list is closed:")
    sweep_case()
    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed")
        sys.exit(1)
    print("OK")
