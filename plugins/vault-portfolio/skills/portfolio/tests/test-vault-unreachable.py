#!/usr/bin/env python3
"""A vault that is SET but unreachable is refused, by every portfolio writer.

Unset is a loud refusal ("portfolio not configured"). Set-but-unreachable — an
unmounted network vault, a stale path, a machine that never had one — is refused
the same way, and this file keeps every writer on the same answer. What makes a
missing vault dangerous is `mkdir(parents=True)`, which will happily build the
whole chain from nothing, so the cases assert the filesystem afterwards, not only
the exit code: a guard fixed while a downstream mkdir survived would pass an
exit-code check and still build a second, empty vault at an unmounted mount point.

`vault_problem()` in portfolio-rebuild.py is the ONE definition of a reachable
vault. A vault is defined by CONTENT: it contains `Portfolio/`, which an empty,
unmounted mountpoint does not. The other writers delegate to it, and the class
sweep at the end fails if a script reads the vault setting without doing so.

The setting comes from _config.vault_setting(): $OBSIDIAN_VAULT_PATH, then
obsidian-wiki's config.json `default_vault`, then the legacy `vault_dir`. Every
case sets it in a throwaway HOME, asserted under the temp tree before anything
runs (under_tmp()).

Stdlib + PyYAML only, no pytest. Run:
  python3 -I src/vault-portfolio/core/skills/portfolio/tests/test-vault-unreachable.py
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"

for _k in list(os.environ):
    if _k.startswith(("OBSIDIAN_", "BUSINESS_", "VAULT_CONTEXT_")):
        os.environ.pop(_k)
os.environ["HOME"] = tempfile.mkdtemp(prefix="unreach-home-")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CORE = load(SCRIPTS / "_config.py", "_unreach_config").PLUGIN_ROOT

# The token every refusal shares, and the invariant tail of the missing-directory
# sentence, lifted from vault_problem() rather than retyped per writer.
TOKEN = "vault unreachable"
CANON = "is not an existing directory — refusing, because a missing vault is not an empty vault"

FAILURES: list[str] = []


def check(ok, msg):
    print(f"  {'ok' if ok else 'FAIL'}: {msg}")
    if not ok:
        FAILURES.append(msg)


def under_tmp(*paths: Path):
    """Refuse to run a case whose fixture escaped the temp tree."""
    tmp = Path(tempfile.gettempdir()).resolve()
    for p in paths:
        rp = Path(p).resolve()
        assert rp == tmp or tmp in rp.parents, f"fixture escaped {tmp}: {rp}"


def make_home(root: Path, vault=None, registry=None, raw=None) -> Path:
    """A throwaway HOME whose obsidian-wiki config.json names `vault` and `registry`."""
    home = root / "home"
    cfg = home / ".config" / "obsidian-wiki" / "config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    body = dict(raw or {})
    if vault is not None:
        body.setdefault("default_vault", str(vault))
    if registry is not None:
        body["registry"] = str(registry)
    cfg.write_text(json.dumps(body))
    return home


def write_registry(path: Path, projects) -> Path:
    path.write_text(yaml.safe_dump({"projects": projects}))
    return path


@contextmanager
def env(**overrides):
    old = {k: os.environ.get(k) for k in overrides}
    for k, v in overrides.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = str(v)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class Outcome:
    """How a call ended: exited, returned, or crashed — kept DISTINCT.

    A refusal reaches the caller as `sys.exit(msg)` from the resolver, or as
    `print(...); return 2` from plan-status-audit's main(). Both count. A raised
    exception is NOT a refusal, however non-zero it would look to a shell: with a
    guard removed, main() reaches a write and dies on FileNotFoundError, and
    scoring that as "refused" would pass the unguarded code.
    """

    def __init__(self, kind, value, out, err, trace=""):
        self.kind, self.value, self.out, self.err, self.trace = kind, value, out, err, trace

    @property
    def refused(self):
        if self.kind == "exit":
            return self.value not in (0, None)
        if self.kind == "return":
            return isinstance(self.value, int) and self.value != 0
        return False

    @property
    def text(self):
        head = self.value if self.kind == "exit" and isinstance(self.value, str) else ""
        return f"{head}\n{self.out}\n{self.err}\n{self.trace}"


def call(fn, *args, argv=None):
    out, err = io.StringIO(), io.StringIO()
    old_argv = sys.argv
    if argv is not None:
        sys.argv = list(argv)
    try:
        with redirect_stdout(out), redirect_stderr(err):
            try:
                res = Outcome("return", fn(*args), "", "")
            except SystemExit as e:
                res = Outcome("exit", e.code if e.code is not None else 0, "", "")
            except Exception as e:
                res = Outcome("raise", e, "", "", trace=f"{type(e).__name__}: {e}")
    finally:
        sys.argv = old_argv
    res.out, res.err = out.getvalue(), err.getvalue()
    return res


# --------------------------------------------------------------------------
# The writers, at their real entry points (in-process).
# --------------------------------------------------------------------------
WRITE_MODULES = ("portfolio-integrate", "portfolio-unify",
                 "portfolio-rebuild", "portfolio-migrate")
# migrate's --project/--all group is required: a bare --write would exit in
# argparse BEFORE the vault guard, and the filesystem checks would pass because
# nothing ran. The wording assertion below catches any such vacuity.
EXTRA_ARGV = {"portfolio-migrate": ["--all"]}


def writer_entry_cases():
    for name in WRITE_MODULES:
        print(f"{name}:")
        mod = load(SCRIPTS / f"{name}.py", name.replace("-", "_"))
        with tempfile.TemporaryDirectory() as root:
            rootp = Path(root)
            missing = rootp / "not-mounted" / "vault"
            under_tmp(missing)
            reg = write_registry(rootp / "registry.yaml", [
                {"path": str(rootp / "repo"), "name": "example-app", "area": "apps"}])
            (rootp / "repo" / "docs").mkdir(parents=True)
            (rootp / "repo" / "docs" / "backlog.md").write_text("# Backlog\n")
            home = make_home(rootp, missing, reg)
            cfg = home / ".config" / "obsidian-wiki" / "config.json"

            with env(HOME=home):
                r = call(mod.vault_dir)
                check(r.refused, f"vault_dir() refuses instead of returning a Path ({r.kind}={r.value!r})")
                check(TOKEN in r.text, f"...with the shared '{TOKEN}' wording")
                check(str(missing) in r.text and str(cfg) in r.text,
                      "...naming both the bad path and the config it came from")

                r = call(mod.main, argv=[f"{name}.py", "--write"] + EXTRA_ARGV.get(name, []))
                check(r.refused, f"main() refuses too — the guard is on the entry path "
                                 f"({r.kind}: {r.trace or r.value!r})")
                check(TOKEN in r.text,
                      f"...and refuses with the vault guard's wording, not some earlier exit "
                      f"({r.text.strip().splitlines()[-1] if r.text.strip() else r.value!r})")
                check(not missing.exists() and not missing.parent.exists(),
                      "...and creates NO part of the missing vault tree")
                check((rootp / "repo" / "docs" / "backlog.md").exists(),
                      "...and leaves the repo's docs/ alone (no fallback write)")

            # Unset is its own message: the operator needs to know whether the
            # setting is missing or wrong.
            with env(HOME=make_home(rootp / "unset", None, reg)):
                r = call(mod.vault_dir)
                check(r.refused and "portfolio not configured" in r.text and TOKEN not in r.text,
                      "an UNSET vault gets the not-configured message, not this one")


def env_override_case():
    """$OBSIDIAN_VAULT_PATH wins, and a missing one is refused, never fallen past."""
    print("$OBSIDIAN_VAULT_PATH:")
    pr = load(SCRIPTS / "portfolio-rebuild.py", "portfolio_rebuild_env")
    with tempfile.TemporaryDirectory() as root:
        rootp = Path(root)
        good = rootp / "good"
        (good / "Portfolio").mkdir(parents=True)
        missing = rootp / "not-mounted" / "vault"
        under_tmp(good, missing)
        home = make_home(rootp, good)
        with env(HOME=home, OBSIDIAN_VAULT_PATH=missing):
            r = call(pr.vault_dir)
        check(r.refused and TOKEN in r.text and "OBSIDIAN_VAULT_PATH" in r.text,
              "a missing $OBSIDIAN_VAULT_PATH is refused by name, even with a good config "
              "below it")
        with env(HOME=home, OBSIDIAN_VAULT_PATH=None):
            r = call(pr.vault_dir)
        check(r.kind == "return" and r.value == good,
              f"without it, config.json's default_vault is used ({r.kind}={r.value!r})")


def expanduser_case():
    """`~/vault` resolves against $HOME, not the cwd (unexpanded it is RELATIVE)."""
    print("expanduser:")
    pr = load(SCRIPTS / "portfolio-rebuild.py", "portfolio_rebuild_expand")
    with tempfile.TemporaryDirectory() as root:
        rootp = Path(root)
        home = make_home(rootp, raw={"default_vault": "~/vault"})
        real = home / "vault"
        (real / "Portfolio").mkdir(parents=True)
        under_tmp(real)
        with env(HOME=home):
            r = call(pr.vault_dir)
        check(r.kind == "return" and r.value == real,
              f"a `~/vault` setting resolves to $HOME/vault and is accepted ({r.kind}={r.value!r})")
        home2 = make_home(rootp / "two", raw={"default_vault": "~/absent"})
        with env(HOME=home2):
            r = call(pr.vault_dir)
        check(r.refused and TOKEN in r.text and str(home2 / "absent") in r.text,
              "...and an expanded path that is still missing is refused, by its expanded name")


# --------------------------------------------------------------------------
def run_script(script: Path, home: Path, args=(), extra_env=None):
    e = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
         "LANG": "C.UTF-8"}
    e.update(extra_env or {})
    return subprocess.run([sys.executable, "-I", str(script), *args],
                          capture_output=True, text=True, timeout=120, env=e,
                          stdin=subprocess.DEVNULL)


CONSUMERS = [
    ("portfolio-rebuild", SCRIPTS / "portfolio-rebuild.py", ["--write"]),
    ("portfolio-unify", SCRIPTS / "portfolio-unify.py", ["--write"]),
    ("portfolio-integrate", SCRIPTS / "portfolio-integrate.py", ["--write"]),
    ("portfolio-migrate", SCRIPTS / "portfolio-migrate.py", ["--all", "--write"]),
    ("plan-status-audit", SCRIPTS / "plan-status-audit.py", ["--fix"]),
]


def unmounted_case():
    """The scenario the guard is named for, which `is_dir()` alone cannot see.

    A mountpoint is a directory whether or not anything is mounted on it, so an
    unmounted vault presents as a local, empty, EXISTING directory. Migrate would
    then build a phantom tree and move a repo's only copy of its docs into it.
    """
    print("unmounted mountpoint — an existing empty dir is not a vault:")
    with tempfile.TemporaryDirectory() as root:
        rootp = Path(root)
        vault = rootp / "mnt" / "vault"
        vault.mkdir(parents=True)                  # the mountpoint, nothing mounted
        under_tmp(vault)
        repo = rootp / "dev" / "example-app"
        (repo / "docs" / "plans").mkdir(parents=True)
        (repo / "docs" / "plans" / "2026-01-01-a-plan.md").write_text("# Plan\n")
        (repo / "docs" / "backlog.md").write_text("# Backlog\n")
        (repo / "docs" / "MATURITY.md").write_text("# Maturity\n")
        reg = write_registry(rootp / "registry.yaml",
                             [{"path": str(repo), "name": "example-app", "area": "apps"}])
        home = make_home(rootp, vault, reg)
        for name, path, args in CONSUMERS:
            r = run_script(path, home, args)
            check(r.returncode != 0 and TOKEN in r.stdout + r.stderr,
                  f"{name}: refuses an unmounted mountpoint (rc={r.returncode})")
        check(not (vault / "Portfolio").exists(), "...and NO part of a phantom vault tree was created")
        survivors = sorted(q.name for q in (repo / "docs").rglob("*") if q.is_file())
        check(survivors == ["2026-01-01-a-plan.md", "MATURITY.md", "backlog.md"],
              f"...and the repo's docs/ is untouched — nothing was moved ({survivors})")

        # Teeth: the same vault WITH Portfolio/ is accepted, so the refusals above
        # are the sentinel firing and not the scripts failing for another reason.
        (vault / "Portfolio").mkdir()
        r = run_script(SCRIPTS / "portfolio-integrate.py", home, ["--write"])
        check(r.returncode == 0 and TOKEN not in r.stdout + r.stderr,
              f"...while the same vault WITH Portfolio/ is accepted (rc={r.returncode})")


# The phrase unique to each branch of vault_problem(). Comparing these rather than a
# bare refuse/accept is what makes a deleted condition visible: a missing branch
# still refuses, one condition later and with a different sentence.
BRANCH_PHRASE = {
    "missing": "is not an existing directory",
    "unmounted (no Portfolio/)": "has no Portfolio/",
    "relative": "relative path",
    "unreadable (OSError)": "could not be read",
}


def branch_parity_case():
    """Every writer classifies every vault shape the same way, with the same phrase."""
    print("branch parity — every writer agrees on every vault shape:")
    with tempfile.TemporaryDirectory() as root:
        rootp = Path(root)
        reg = write_registry(rootp / "registry.yaml", [
            {"path": str(rootp / "repo"), "name": "example-app", "area": "apps"}])
        outer = rootp / "outer"
        unreadable = outer / "vault"
        (unreadable / "Portfolio").mkdir(parents=True)
        unmounted = rootp / "mnt" / "vault"
        unmounted.mkdir(parents=True)
        under_tmp(unreadable, unmounted)
        shapes = [
            ("missing", str(rootp / "not-mounted" / "vault"), None),
            ("unmounted (no Portfolio/)", str(unmounted), None),
            ("relative", "somevault", None),
            ("unreadable (OSError)", str(unreadable), outer),
        ]
        for label, value, chmod_target in shapes:
            home = make_home(rootp / label.split()[0], raw={"default_vault": value}, registry=reg)
            if chmod_target:
                os.chmod(chmod_target, 0o000)
            try:
                verdicts = {}
                for name, path, args in CONSUMERS:
                    r = run_script(path, home, args)
                    blob = r.stdout + r.stderr
                    verdicts[name] = (r.returncode != 0, TOKEN in blob and BRANCH_PHRASE[label] in blob,
                                      "Traceback (most recent call last)" in blob)
            finally:
                if chmod_target:
                    os.chmod(chmod_target, 0o755)
            check(all(v[0] for v in verdicts.values()),
                  f"{label}: every writer refuses (not: "
                  f"{[n for n, v in verdicts.items() if not v[0]] or 'none'})")
            check(all(v[1] for v in verdicts.values()),
                  f"{label}: ...with the shared refusal and this branch's phrase "
                  f"({[n for n, v in verdicts.items() if not v[1]] or 'none'} missing it)")
            check(not any(v[2] for v in verdicts.values()),
                  f"{label}: ...and none of them crashes instead of refusing "
                  f"({[n for n, v in verdicts.items() if v[2]] or 'none'})")

        # A setting that is not a string is refused by the config module itself,
        # by name, before any path exists to check.
        home = make_home(rootp / "notastring", raw={"default_vault": 12345}, registry=reg)
        bad = []
        for name, path, args in CONSUMERS:
            r = run_script(path, home, args)
            blob = r.stdout + r.stderr
            if not (r.returncode != 0 and "default_vault must be a string" in blob
                    and "Traceback" not in blob):
                bad.append(name)
        check(not bad, f"a non-string default_vault is refused by name, no traceback ({bad or 'none'})")

        reachable = rootp / "good"
        (reachable / "Portfolio").mkdir(parents=True)
        home = make_home(rootp / "good-home", reachable, reg)
        refused = [n for n, path, args in CONSUMERS if TOKEN in (lambda r: r.stdout + r.stderr)(
            run_script(path, home, args))]
        check(not refused, f"reachable vault: every writer ACCEPTS it — the refusals above "
                           f"discriminate ({refused or 'none'} refused)")


def bad_value_in_process_case():
    """vault_problem() itself: a non-Path value gets the shared refusal, not a TypeError."""
    print("vault_problem() on a value that is not a path:")
    pr = load(SCRIPTS / "portfolio-rebuild.py", "portfolio_rebuild_badval")
    path, problem = pr.vault_problem(12345, "test")
    check(path is None and problem and TOKEN in problem and "must be a path" in problem,
          f"a non-path value is refused with the shared wording ({problem!r})")


def override_case():
    """plan-status-audit's --vault bypasses the config; it may not bypass the rule."""
    print("plan-status-audit --vault:")
    mod = load(SCRIPTS / "plan-status-audit.py", "plan_status_audit")
    with tempfile.TemporaryDirectory() as root:
        rootp = Path(root)
        missing = rootp / "not-mounted" / "vault"
        under_tmp(missing)
        reg = write_registry(rootp / "registry.yaml", [
            {"path": str(rootp / "repo"), "name": "example-app", "area": "apps"}])
        with env(HOME=make_home(rootp, None, reg)):
            r = call(mod.main, argv=["plan-status-audit.py", "--vault", str(missing),
                                     "--registry", str(reg), "--fix"])
        check(r.refused, f"--vault at a missing directory is refused ({r.kind}: {r.trace or r.value!r})")
        check(TOKEN in r.text and "--vault" in r.text, "...naming the flag as the source")
        check(not missing.exists(), "...and no .audit-backups tree is created under it")


# Every script that reads the registry, writers and read-only scanners alike. The
# scanners matter as much as the writers: their JSON is what the skills and the
# roll-ups render, so a silently smaller project list there is a wrong answer too.
REGISTRY_READERS = CONSUMERS + [
    ("compass-scan", CORE / "skills" / "compass" / "scripts" / "compass-scan.py", []),
    ("security-scan", SCRIPTS / "security-scan.py", []),
]

# The phrase each registry refusal carries. The registry's own file name contains
# the word "registry", so that word alone proves nothing about WHY it was refused.
ENTRY_PHRASE = "needs string name, area and path"


def registry_cases():
    """A missing or malformed registry is a clean refusal: never a traceback, never
    read as an empty portfolio (a roll-up regenerated from zero projects would
    replace every row with nothing), and never a silently smaller project list."""
    print("registry — missing or malformed is refused, never read as empty:")
    with tempfile.TemporaryDirectory() as root:
        rootp = Path(root)
        vault = rootp / "vault"
        (vault / "Portfolio" / "apps" / "example-app" / "plans").mkdir(parents=True)
        (vault / "Portfolio" / "apps" / "example-app" / "plans" / "2026-01-01-a-plan.md").write_text(
            "### Task 1.1: a\n- **Status:** [x]\n")
        good = f"  - name: example-app\n    area: apps\n    path: {rootp}\n"
        bodies = {
            "missing": (None, "not found"),
            "not yaml": ("projects: [unclosed\n", "is not valid YAML"),
            "not utf-8": (b"projects:\n  - name: \xff\xfe\n", "could not be read"),
            "no projects list": ("projects: 3\n", "has no `projects:` list"),
            "an entry without an area": (
                f"projects:\n  - name: example-app\n    path: {rootp}\n", ENTRY_PHRASE),
            "an entry without a path": (
                "projects:\n  - name: example-app\n    area: apps\n", ENTRY_PHRASE),
            "a non-dict entry": ("projects:\n" + good + "  - example-app\n", ENTRY_PHRASE),
        }
        for label, (body, phrase) in bodies.items():
            reg = rootp / f"registry-{label.replace(' ', '-')}.yaml"
            if isinstance(body, bytes):
                reg.write_bytes(body)
            elif body is not None:
                reg.write_text(body)
            home = make_home(rootp / f"h-{label.replace(' ', '-')}", vault, reg)
            before = sorted((p.as_posix(), p.read_bytes() if p.is_file() else b"")
                            for p in vault.rglob("*"))
            bad = []
            for name, path, args in REGISTRY_READERS:
                r = run_script(path, home, args)
                blob = r.stdout + r.stderr
                if (r.returncode == 0 or "registry" not in blob or phrase not in blob
                        or str(reg) not in blob
                        or "Traceback (most recent call last)" in blob):
                    bad.append(f"{name} rc={r.returncode}: {blob.strip().splitlines()[-1:] }")
            after = sorted((p.as_posix(), p.read_bytes() if p.is_file() else b"")
                           for p in vault.rglob("*"))
            check(not bad, f"{label} registry: every reader refuses with '{phrase}', naming "
                           f"the registry, no traceback ({bad or 'none'})")
            check(before == after, f"{label} registry: ...and the vault is unchanged")


def registry_sweep_case():
    """The class claim: ONE registry validator, and every reader goes through it.

    `registry_path(` / `registry_file(` is how a script finds the registry. A script
    that finds it without calling the validator reads it by its own rules, which is
    how four readers came to disagree about what a valid entry is. The validator is
    registry_problem(), whose checks load_projects() wraps for the callers that exit
    with the shared message; a reader calls one of the two.
    """
    print("class sweep — every registry reader calls the one validator:")
    import ast
    locators = {"skills/portfolio/scripts/_config.py", "scripts/lib/registry_path.py"}
    validators = {"load_projects", "registry_problem"}
    readers, rogue = [], []
    defs = {name: [] for name in validators}
    wraps = False
    for path in sorted(CORE.rglob("*.py")):
        rel = path.relative_to(CORE).as_posix()
        if "/tests/" in f"/{rel}" or "__pycache__" in rel or rel.startswith("vendor/"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = {getattr(n.func, "attr", getattr(n.func, "id", None))
                 for n in ast.walk(tree) if isinstance(n, ast.Call)}
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name in validators:
                defs[n.name].append(rel)
                if n.name == "load_projects":
                    wraps = any(isinstance(c, ast.Call) and getattr(c.func, "id", None)
                                == "registry_problem" for c in ast.walk(n))
        if rel in locators:
            continue
        if calls & {"registry_path", "registry_file"}:
            readers.append(rel)
            if not calls & validators:
                rogue.append(rel)
    check({"skills/compass/scripts/compass-scan.py", "skills/portfolio/scripts/security-scan.py",
           "scripts/records-home.py"} <= set(readers),
          f"the sweep sees the scanners and the resolver as registry readers ({readers})")
    check(not rogue, f"no script finds the registry without load_projects() or "
                     f"registry_problem() (rogue: {rogue or 'none'})")
    check(all(d == ["skills/portfolio/scripts/portfolio-rebuild.py"] for d in defs.values()),
          f"load_projects() and registry_problem() are each defined exactly once ({defs})")
    check(wraps, "load_projects() calls registry_problem(): one set of checks, not two")


def sweep_case():
    """The class claim: every script that reads the vault setting delegates the check.

    `vault_setting(` is how a script reads the setting; vault_problem() is the one
    definition of a reachable vault. A script that reads the setting without calling
    vault_problem()/require_vault() is a second definition, free to drift. Scripts
    that reach the vault through portfolio-rebuild's vault_dir() never name
    vault_setting( and are covered by the cases above.
    """
    print("class sweep — every reader of the vault setting delegates:")
    readers, rogue = [], []
    for path in sorted(CORE.rglob("*.py")):
        rel = path.relative_to(CORE).as_posix()
        if "/tests/" in f"/{rel}" or "__pycache__" in rel or rel.startswith("vendor/"):
            continue
        if rel == "skills/portfolio/scripts/_config.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"\bvault_setting\(", text):
            readers.append(rel)
            if not re.search(r"\b(vault_problem|require_vault)\(", text):
                rogue.append(rel)
    check("skills/portfolio/scripts/portfolio-rebuild.py" in readers,
          f"the sweep sees the one definition's own reader ({readers})")
    check(not rogue, f"no script reads the vault setting without vault_problem() "
                     f"(rogue: {rogue or 'none'})")
    # The sentence is written as adjacent f-string fragments; collapse whitespace,
    # then drop the quote seams, so a sentence split across lines still matches.
    squashed = " ".join((SCRIPTS / "portfolio-rebuild.py").read_text(encoding="utf-8").split())
    for seam in ('" f"', '" "'):
        squashed = squashed.replace(seam, "")
    check(CANON in squashed, "vault_problem() carries the whole shared sentence")
    defs = [p.relative_to(CORE).as_posix() for p in CORE.rglob("*.py")
            if "/tests/" not in f"/{p.relative_to(CORE).as_posix()}"
            and re.search(r"(?m)^def vault_problem\(", p.read_text(encoding="utf-8", errors="replace"))]
    check(defs == ["skills/portfolio/scripts/portfolio-rebuild.py"],
          f"vault_problem() is defined exactly once ({defs})")


if __name__ == "__main__":
    writer_entry_cases()
    env_override_case()
    expanduser_case()
    unmounted_case()
    branch_parity_case()
    bad_value_in_process_case()
    override_case()
    registry_cases()
    registry_sweep_case()
    sweep_case()
    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed")
        sys.exit(1)
    print("OK")
