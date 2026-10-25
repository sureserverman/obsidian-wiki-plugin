#!/usr/bin/env python3
"""records-home.py answers the records-resolver contract, and writes only when asked.

The contract a caller relies on is three exit codes and one stdout line:

  0  stdout is exactly one absolute line, <vault>/Portfolio/<area>/<name>
  3  unmanaged: no vault configured, no area/name derivable, or the project's
     registry entry says `records: repo`. stderr names which.
  2  configured but unreachable, or an input that does not parse. Nothing created.

Every run here is a subprocess on a throwaway HOME and a synthetic vault. The
whole temp tree (HOME, vault, registry, repos) is hashed around each run that must
not write, so a stray file anywhere counts, not only in the place a reader thinks
of checking.

Stdlib + PyYAML, no pytest. Run:
  python3 -I src/vault-portfolio/core/scripts/tests/test-records-home.py
"""
from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "records-home.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_config = _load(HERE.parent.parent / "skills" / "portfolio" / "scripts" / "_config.py",
                "_records_home_test_config")
protocol = _load(_config.PLUGIN_ROOT / "scripts" / "lib" / "vault_write_protocol.py",
                 "_records_home_test_protocol")

FAILURES: list[str] = []
BEGIN_MARK = "PORTFOLIO-STATUS-BEGIN"


def check(ok, msg):
    print(f"  {'ok' if ok else 'FAIL'}: {msg}")
    if not ok:
        FAILURES.append(msg)


# --------------------------------------------------------------------------
# A synthetic world
# --------------------------------------------------------------------------
class World:
    """tmp/home (HOME), tmp/v (the vault), tmp/dev/<area>/<name> (repos)."""

    def __init__(self, tmp: Path, vault=True, portfolio=True, config=True):
        self.tmp = tmp
        self.home = tmp / "home"
        self.home.mkdir()
        self.vault = tmp / "v"
        if vault:
            self.vault.mkdir()
            if portfolio:
                (self.vault / "Portfolio").mkdir()
        self.cfg = self.home / ".config" / "obsidian-wiki" / "config.json"
        if config:
            self.write_config({"default_vault": str(self.vault)})
        self.registry = self.home / ".config" / "obsidian-wiki" / "projects-registry.yaml"

    def write_config(self, data):
        self.cfg.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.write_text(data if isinstance(data, str) else json.dumps(data),
                            encoding="utf-8")

    def repo(self, area="apps", name="example-app", git=True, files=()):
        path = self.tmp / "dev" / area / name
        path.mkdir(parents=True)
        if git:
            subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "init", "-q",
                            "--template=", str(path)], check=True)
        for f in files:
            (path / f).write_text("", encoding="utf-8")
        return path

    def register(self, *entries):
        lines = ["version: 1", "", "projects:"]
        for e in entries:
            first = True
            for k, v in e.items():
                lines.append(f"  {'- ' if first else '  '}{k}: {v}")
                first = False
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        self.registry.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def env(self, **extra):
        env = {"HOME": str(self.home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
               "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
        env.update(extra)
        return env

    def run(self, *argv, cwd="/", **extra):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, argv)],
                              capture_output=True, text=True, timeout=60,
                              env=self.env(**extra), cwd=cwd, stdin=subprocess.DEVNULL)

    def start(self, *argv, **extra):
        return subprocess.Popen([sys.executable, "-I", str(SCRIPT), *map(str, argv)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                env=self.env(**extra), cwd="/", stdin=subprocess.DEVNULL)

    def entries(self, repo):
        data = yaml.safe_load(self.registry.read_text(encoding="utf-8")) or {}
        return [p for p in data.get("projects") or [] if p.get("path") == str(repo)]

    def digest(self) -> str:
        h = hashlib.sha256()
        for p in sorted(self.tmp.rglob("*")):
            rel = p.relative_to(self.tmp).as_posix()
            h.update(rel.encode() + b"\0")
            if p.is_file() and not p.is_symlink():
                h.update(p.read_bytes())
            h.update(b"\1")
        return h.hexdigest()


def world(**kw):
    td = tempfile.TemporaryDirectory()
    return td, World(Path(td.name), **kw)


def one_line(r) -> str | None:
    """stdout's single line, or None when stdout is not exactly one line."""
    out = r.stdout
    if not out.endswith("\n") or out.count("\n") != 1:
        return None
    return out[:-1]


# --------------------------------------------------------------------------
# Exit 0: the read path
# --------------------------------------------------------------------------
def case_read_unregistered():
    print("read, unregistered repo: area/name from the last two path segments")
    td, w = world()
    with td:
        repo = w.repo()
        before = w.digest()
        r = w.run("--project", repo)
        check(r.returncode == 0, f"exits 0 (rc={r.returncode}: {r.stderr.strip()})")
        check(one_line(r) == f"{w.vault}/Portfolio/apps/example-app",
              f"stdout is exactly one line, the home ({r.stdout!r})")
        check(os.path.isabs(r.stdout.strip()), "the line is absolute")
        check(w.digest() == before,
              "nothing is created or registered: HOME, vault, registry and repo unchanged")


def case_read_registered():
    print("read, registered repo: area/name come from the registry entry")
    td, w = world()
    with td:
        repo = w.repo()
        w.register({"path": repo, "name": "renamed-app", "area": "tools", "enabled": "true"})
        (w.vault / "Portfolio" / "tools" / "renamed-app").mkdir(parents=True)
        before = w.digest()
        r = w.run("--project", repo)
        check(r.returncode == 0, f"exits 0 (rc={r.returncode}: {r.stderr.strip()})")
        check(one_line(r) == f"{w.vault}/Portfolio/tools/renamed-app",
              f"the registry's area and name win over the path ({r.stdout!r})")
        check(w.digest() == before,
              "a read on a registered repo writes no sidecar and changes nothing")


# --------------------------------------------------------------------------
# Exit 3: unmanaged
# --------------------------------------------------------------------------
def case_unconfigured():
    print("no vault configured: exit 3, in every mode")
    td, w = world(vault=False, config=False)
    with td:
        repo = w.repo(files=["Cargo.toml"])
        before = w.digest()
        for mode in ([], ["--for-write"], ["--decision-registers"]):
            r = w.run("--project", repo, *mode)
            label = " ".join(mode) or "read"
            check(r.returncode == 3, f"{label}: exits 3 (rc={r.returncode}: {r.stderr.strip()})")
            check(r.stdout == "", f"{label}: prints nothing on stdout")
            check("not configured" in r.stderr, f"{label}: stderr says the vault is not "
                                                f"configured ({r.stderr.strip()})")
        check(w.digest() == before, "nothing is created")


def case_underivable():
    print("no area/name derivable: exit 3, and --for-write creates nothing")
    td, w = world()
    with td:
        before = w.digest()
        for mode in ([], ["--for-write"]):
            r = w.run("--project", "/", *mode)
            label = " ".join(mode) or "read"
            check(r.returncode == 3, f"{label}: exits 3 (rc={r.returncode}: {r.stderr.strip()})")
            check("area and a name" in r.stderr,
                  f"{label}: stderr says no area/name could be derived ({r.stderr.strip()})")
        check(w.digest() == before, "nothing is created")


def case_opt_out():
    print("registry entry `records: repo`: exit 3 in both modes, nothing written")
    td, w = world()
    with td:
        repo = w.repo(files=["Cargo.toml"])
        (w.vault / "Portfolio/decisions").mkdir()
        (w.vault / "Portfolio/decisions" / "rust.md").write_text("# rust\n")
        w.register({"path": repo, "name": "example-app", "area": "apps", "enabled": "true",
                    "records": "repo"})
        before = w.digest()
        for mode in ([], ["--for-write"], ["--decision-registers"]):
            r = w.run("--project", repo, *mode)
            label = " ".join(mode) or "read"
            check(r.returncode == 3, f"{label}: exits 3 (rc={r.returncode}: {r.stderr.strip()})")
            check(r.stdout == "", f"{label}: prints nothing on stdout ({r.stdout!r})")
            check("records: repo" in r.stderr,
                  f"{label}: stderr names the opt-out ({r.stderr.strip()})")
            check(w.digest() == before,
                  f"{label}: vault, registry and repo hash unchanged (no home, no "
                  f"registration, no sidecar)")
        # The opt-out is a property of the project, so it holds with the vault gone too.
        shutil.rmtree(w.vault / "Portfolio")
        r = w.run("--project", repo, "--for-write")
        check(r.returncode == 3, f"opt-out with the vault unreachable is still exit 3 "
                                 f"(rc={r.returncode})")


# --------------------------------------------------------------------------
# Exit 2: configured but unreachable, or unparseable
# --------------------------------------------------------------------------
def case_unreachable():
    print("configured but unreachable: exit 2, nothing created")
    cases = [
        ("config names a missing vault", dict(vault=False), {}),
        ("vault without Portfolio/ (an unmounted mountpoint)", dict(portfolio=False), {}),
        ("OBSIDIAN_VAULT_PATH names a missing directory", dict(),
         {"OBSIDIAN_VAULT_PATH": "MISSING"}),
    ]
    for label, kw, env in cases:
        td, w = world(**kw)
        with td:
            repo = w.repo(files=["Cargo.toml"])
            env = {k: (str(w.tmp / "nowhere") if v == "MISSING" else v) for k, v in env.items()}
            before = w.digest()
            for mode in ([], ["--for-write"], ["--decision-registers"]):
                r = w.run("--project", repo, *mode, **env)
                m = " ".join(mode) or "read"
                check(r.returncode == 2, f"{label}, {m}: exits 2 (rc={r.returncode}: "
                                         f"{r.stderr.strip()[:120]})")
                check(r.stdout == "", f"{label}, {m}: prints nothing on stdout")
                check("unreachable" in r.stderr, f"{label}, {m}: stderr says unreachable")
            check(w.digest() == before, f"{label}: nothing is created")


def case_unparseable():
    print("an input that does not parse: exit 2, never a guess")
    td, w = world()
    with td:
        repo = w.repo()
        w.write_config("{not json")
        r = w.run("--project", repo)
        check(r.returncode == 2, f"malformed config.json: exits 2 (rc={r.returncode})")
    td, w = world()
    with td:
        repo = w.repo()
        w.registry.write_text("projects: [unclosed\n", encoding="utf-8")
        before = w.digest()
        for mode in ([], ["--for-write"], ["--decision-registers"], ["--all-homes"]):
            args = mode if mode == ["--all-homes"] else ["--project", repo, *mode]
            r = w.run(*args)
            m = " ".join(mode) or "read"
            check(r.returncode == 2, f"malformed registry, {m}: exits 2 (rc={r.returncode})")
            check(r.stderr.startswith(f"records-home: registry {w.registry} is broken:")
                  and "not configured" not in r.stderr and "Traceback" not in r.stderr
                  and r.stdout == "",
                  f"malformed registry, {m}: one records-home line says the registry is "
                  f"broken, not unconfigured ({r.stderr.strip()[:160]!r})")
        check(w.digest() == before, "malformed registry: nothing written")
    td, w = world()
    with td:
        repo = w.repo()
        w.register({"path": repo, "name": "example-app", "area": "apps", "records": "elsewhere"})
        r = w.run("--project", repo)
        check(r.returncode == 2, f"an unknown `records:` value: exits 2 (rc={r.returncode})")
        check("`records: 'elsewhere'`" in r.stderr and "`repo`" in r.stderr,
              f"...naming the value and the one value understood ({r.stderr.strip()[:200]})")
        other = w.repo(name="example-cli")
        r = w.run("--project", other)
        check(r.returncode == 2 and "records" in r.stderr,
              f"...and refused for every repo, not only the entry that carries it, as "
              f"every other script refuses it (rc={r.returncode})")
    td, w = world()
    with td:
        repo = w.repo()
        w.register({"path": repo, "name": "..", "area": "apps"})
        before = w.digest()
        r = w.run("--project", repo, "--for-write")
        check(r.returncode == 2, f"a registry name that is not one folder name: exits 2 "
                                 f"(rc={r.returncode})")
        check(w.digest() == before, "...and nothing is written")
    td, w = world()
    with td:
        repo = w.repo()
        r = w.run("--project", repo, "--for-write", "--decision-registers")
        check(r.returncode == 2, f"--for-write with --decision-registers: usage, exit 2 "
                                 f"(rc={r.returncode})")


# --------------------------------------------------------------------------
# --for-write
# --------------------------------------------------------------------------
def case_for_write_fresh():
    print("--for-write on a fresh repo: home, registry line and sidecar block")
    td, w = world()
    with td:
        repo = w.repo()
        other = w.repo(name="example-cli")
        w.register({"path": other, "name": "example-cli", "area": "apps", "enabled": "true",
                    "added": "2026-01-01"})
        original = w.registry.read_bytes()
        r = w.run("--project", repo, "--for-write")
        home = w.vault / "Portfolio" / "apps" / "example-app"
        check(r.returncode == 0, f"exits 0 (rc={r.returncode}: {r.stderr.strip()})")
        check(one_line(r) == str(home), f"stdout is exactly one line, the home ({r.stdout!r})")
        check(home.is_dir(), "the home is created")
        text = w.registry.read_text(encoding="utf-8")
        check(w.registry.read_bytes().startswith(original),
              "the registry is appended to, never rewritten (the old bytes are a prefix)")
        projects = (yaml.safe_load(text) or {}).get("projects") or []
        mine = [p for p in projects if p.get("path") == str(repo)]
        check(len(mine) == 1 and mine[0].get("name") == "example-app"
              and mine[0].get("area") == "apps" and mine[0].get("enabled") is True
              and mine[0].get("added") == dt.date.today(),
              f"one entry with path, name, area, enabled: true and added: today ({mine})")
        check(f"path: {repo}" in text, "the entry's path line is greppable as written")
        sidecar = repo / ".claude" / "vault-context.md"
        check(sidecar.is_file() and BEGIN_MARK in sidecar.read_text(encoding="utf-8")
              and str(home) in sidecar.read_text(encoding="utf-8"),
              "the repo's sidecar carries the PORTFOLIO-STATUS block naming the home")
        check(not (other / ".claude").exists(), "no other project's sidecar is touched")
        r2 = w.run("--project", repo, "--for-write")
        projects = (yaml.safe_load(w.registry.read_text(encoding="utf-8")) or {})["projects"]
        check(r2.returncode == 0 and sum(p.get("path") == str(repo) for p in projects) == 1,
              "a second --for-write registers nothing new")
    td, w = world()
    with td:
        repo = w.repo()
        r = w.run("--project", repo, "--for-write")
        check(r.returncode == 0 and w.registry.is_file(),
              f"with no registry yet, --for-write creates it (rc={r.returncode}: "
              f"{r.stderr.strip()})")
        data = yaml.safe_load(w.registry.read_text(encoding="utf-8")) if w.registry.is_file() else {}
        check(isinstance(data, dict) and [p.get("path") for p in data.get("projects") or []]
              == [str(repo)], f"...holding exactly this project ({data})")


def case_for_write_grouping_folder():
    print("--for-write on a grouping folder: exit 2, nothing written")
    td, w = world()
    with td:
        repo = w.repo()
        w.register({"path": repo, "name": "example-app", "area": "apps", "enabled": "true"})
        area_dir = repo.parent
        before = w.digest()
        r = w.run("--project", area_dir, "--for-write")
        check(r.returncode == 2, f"exits 2 (rc={r.returncode})")
        check("area directory" in r.stderr,
              f"stderr carries the containment rule's refusal ({r.stderr.strip()[:120]})")
        check(r.stdout == "", "prints nothing on stdout")
        check(w.digest() == before, "vault, registry and repos unchanged")


def case_for_write_foreign_window():
    print("--for-write under another owner's maintenance window: refused")
    td, w = world()
    with td:
        repo = w.repo()
        protocol.start(w.vault.resolve(), owner="another-owner", purpose="test window",
                       lease_seconds=3600)
        before = w.digest()
        r = w.run("--project", repo, "--for-write")
        check(r.returncode != 0, f"exits non-zero (rc={r.returncode})")
        check("maintenance window" in r.stderr, f"stderr carries the protocol's refusal "
                                                f"({r.stderr.strip()[:120]})")
        check("Traceback" not in r.stderr, "no traceback")
        check(w.digest() == before, "vault, registry and repo unchanged")


def case_for_write_broken_integration():
    print("--for-write with an integration.md that does not parse: exit 2, nothing created")
    # The sidecar's edge lines come from the home's integration.md. A file that cannot
    # be read is refused before the registry append and the home mkdir, not after.
    for label, registered_other in (("registry present", True), ("no registry yet", False)):
        td, w = world()
        with td:
            repo = w.repo()
            if registered_other:
                other = w.repo(name="example-cli")
                w.register({"path": other, "name": "example-cli", "area": "apps",
                            "enabled": "true"})
            home = w.vault / "Portfolio" / "apps" / "example-app"
            home.mkdir(parents=True)
            bad = home / "integration.md"
            bad.write_text("---\ndepends_on: [\"[[example-cli]]\"\n---\n", encoding="utf-8")
            before = w.digest()
            r = w.run("--project", repo, "--for-write")
            check(r.returncode == 2, f"{label}: exits 2 (rc={r.returncode}: {r.stderr.strip()})")
            check(str(bad) in r.stderr and "not valid YAML" in r.stderr
                  and "unexpected failure" not in r.stderr and "Traceback" not in r.stderr,
                  f"{label}: stderr names the file and why ({r.stderr.strip()[:200]})")
            check(r.stdout == "", f"{label}: prints nothing on stdout")
            check(w.digest() == before, f"{label}: registry, vault and repo byte-identical")


def case_relative_project():
    print("a relative --project is resolved against the working directory")
    td, w = world()
    with td:
        w.repo()
        r = w.run("--project", "apps/example-app", cwd=w.tmp / "dev")
        check(r.returncode == 0 and one_line(r) == f"{w.vault}/Portfolio/apps/example-app",
              f"exits 0 with the absolute home (rc={r.returncode}: {r.stdout!r} "
              f"{r.stderr.strip()})")


def case_registry_shapes():
    print("registry shapes: comments and CRLF append; an unappendable shape refuses")
    td, w = world()
    with td:
        repo = w.repo()
        other = w.repo(name="example-cli")
        w.registry.parent.mkdir(parents=True, exist_ok=True)
        w.registry.write_bytes(
            (f"# the registry\nversion: 1\n\nprojects:  # one per repo\n"
             f"  # the cli first\n  - path: {other}\n    name: example-cli\n"
             f"    area: apps  # an area\n# trailing comment\n").encode())
        old = w.registry.read_bytes()
        r = w.run("--project", repo, "--for-write")
        check(r.returncode == 0 and w.registry.read_bytes().startswith(old)
              and len(w.entries(repo)) == 1 and len(w.entries(other)) == 1,
              f"a commented registry: appended, its bytes kept as a prefix "
              f"(rc={r.returncode}: {r.stderr.strip()})")
    td, w = world()
    with td:
        repo = w.repo()
        other = w.repo(name="example-cli")
        w.registry.parent.mkdir(parents=True, exist_ok=True)
        w.registry.write_bytes((f"version: 1\r\nprojects:\r\n  - path: {other}\r\n"
                                f"    name: example-cli\r\n    area: apps\r\n").encode())
        old = w.registry.read_bytes()
        r = w.run("--project", repo, "--for-write")
        new = w.registry.read_bytes()
        check(r.returncode == 0 and new.startswith(old),
              f"a CRLF registry: the old bytes stay a prefix (rc={r.returncode}: "
              f"{r.stderr.strip()})")
        check(b"\n" not in new.replace(b"\r\n", b""),
              "...and the appended lines keep its CRLF line ends")
        check(len(w.entries(repo)) == 1 and len(w.entries(other)) == 1,
              "...and it parses with both entries")
    shapes = [
        ("`projects: []` in flow style", lambda o: "version: 1\nprojects: []\n"),
        ("`projects:` followed by another key",
         lambda o: (f"projects:\n  - path: {o}\n    name: example-cli\n    area: apps\n"
                    f"version: 1\n")),
    ]
    for label, text in shapes:
        td, w = world()
        with td:
            repo = w.repo()
            other = w.repo(name="example-cli")
            w.registry.parent.mkdir(parents=True, exist_ok=True)
            w.registry.write_text(text(other), encoding="utf-8")
            before = w.digest()
            old = w.registry.read_bytes()
            r = w.run("--project", repo, "--for-write")
            check(r.returncode == 2, f"{label}: exits 2 (rc={r.returncode})")
            check("add this entry by hand" in r.stderr and f"path: {repo}" in r.stderr,
                  f"{label}: stderr prints the entry for a manual add "
                  f"({r.stderr.strip()[-160:]})")
            check(w.registry.read_bytes() == old, f"{label}: the registry is byte-identical")
            check(not (w.vault / "Portfolio" / "apps").exists(),
                  f"{label}: no home is created")
            check(w.digest() == before, f"{label}: nothing else is written")


def blocked_in_flock(pid) -> bool | None:
    """Whether the process is asleep in flock(): True, False, or None without /proc."""
    try:
        wchan = Path(f"/proc/{pid}/wchan").read_text()
    except OSError:
        return None
    return "lock" in wchan


def wait_blocked(procs, timeout=10.0):
    """The first of `procs` seen asleep in flock() within `timeout`, else None."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for p in procs:
            if p.poll() is None and blocked_in_flock(p.pid):
                return p
        time.sleep(0.02)
    return None


def finish(procs):
    out = []
    for p in procs:
        o, e = p.communicate(timeout=60)
        out.append((p.returncode, o, e.strip()))
    return out


def case_concurrent_register():
    print("two --for-write runs at once: the registry lock keeps both entries, once each")
    delay = 1.0
    env = {"VAULT_PORTFOLIO_TEST_APPEND_DELAY": str(delay)}
    check(Path("/proc/self/wchan").exists(),
          "/proc/<pid>/wchan is readable, so a wait on the registry lock can be observed")
    for label, seed in (("registry present", True), ("no registry yet", False)):
        td, w = world()
        with td:
            one = w.repo(name="example-one")
            two = w.repo(name="example-two")
            if seed:
                w.register({"path": w.repo(name="example-cli"), "name": "example-cli",
                            "area": "apps"})
            t0 = time.monotonic()
            procs = [w.start("--project", repo, "--for-write", **env) for repo in (one, two)]
            waiter = wait_blocked(procs)
            results = finish(procs)
            wall = time.monotonic() - t0
            check(waiter is not None,
                  f"{label}: one run was seen asleep in flock() while the other held the lock")
            check(wall >= 2 * delay - 0.1,
                  f"{label}: the pair took {wall:.2f} s, at least two {delay} s appends end to "
                  f"end, so the appends did not overlap")
            check([r[0] for r in results] == [0, 0],
                  f"{label}: both runs exit 0 ({[(r[0], r[2][:120]) for r in results]})")
            check(len(w.entries(one)) == 1 and len(w.entries(two)) == 1,
                  f"{label}: both repos are registered, once each (one: "
                  f"{len(w.entries(one))}, two: {len(w.entries(two))})")
            data = yaml.safe_load(w.registry.read_text(encoding="utf-8"))
            check(isinstance(data, dict) and data.get("version") == 1
                  and len(data.get("projects") or []) == (3 if seed else 2),
                  f"{label}: the registry parses with every entry ({data})")
    td, w = world()
    with td:
        repo = w.repo()
        w.register({"path": w.repo(name="example-cli"), "name": "example-cli",
                    "area": "apps"})
        procs = [w.start("--project", repo, "--for-write", **env) for _ in range(2)]
        waiter = wait_blocked(procs)
        results = finish(procs)
        check(waiter is not None, "the same repo twice: one run waits on the lock")
        check([r[0] for r in results] == [0, 0] and len(w.entries(repo)) == 1,
              f"the same repo twice at once: one entry, not two (rcs "
              f"{[r[0] for r in results]}, entries {len(w.entries(repo))})")
        check([r[1] for r in results] == [f"{w.vault}/Portfolio/apps/example-app\n"] * 2,
              f"...and both print the one home ({[r[1] for r in results]})")


def case_register_race_effective_entry():
    print("an entry another writer adds while --for-write waits: its area and name win")
    td, w = world()
    with td:
        repo = w.repo()
        w.register({"path": w.repo(name="example-cli"), "name": "example-cli",
                    "area": "apps"})
        folder = w.registry.parent
        fd = os.open(folder, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            proc = w.start("--project", repo, "--for-write")
            waiter = wait_blocked([proc])
            check(waiter is proc,
                  "the run read the registry (no entry yet) and now waits on the lock")
            with open(w.registry, "a", encoding="utf-8") as fh:
                fh.write(f"  - path: {repo}\n    name: renamed-app\n    area: tools\n"
                         f"    enabled: true\n")
        finally:
            os.close(fd)
        (rc, out, err), = finish([proc])
        theirs = w.vault / "Portfolio" / "tools" / "renamed-app"
        check(rc == 0 and out == f"{theirs}\n",
              f"the home printed is the other writer's entry's (rc={rc}: {out!r} {err[:160]})")
        check(theirs.is_dir() and not (w.vault / "Portfolio" / "apps").exists(),
              "...and that is the home created; none is made from the path")
        check(len(w.entries(repo)) == 1, f"no second entry is appended ({w.entries(repo)})")
        sidecar = repo / ".claude" / "vault-context.md"
        check(sidecar.is_file() and str(theirs) in sidecar.read_text(encoding="utf-8"),
              "the sidecar names that home")
    td, w = world()
    with td:
        repo = w.repo()
        w.register({"path": w.repo(name="example-cli"), "name": "example-cli",
                    "area": "apps"})
        fd = os.open(w.registry.parent, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            proc = w.start("--project", repo, "--for-write")
            check(wait_blocked([proc]) is proc, "a second run waits on the lock")
            with open(w.registry, "a", encoding="utf-8") as fh:
                fh.write(f"  - path: {repo}\n    name: example-app\n    area: apps\n"
                         f"    records: repo\n")
        finally:
            os.close(fd)
        before = w.vault.joinpath("Portfolio").exists() and sorted(
            p.name for p in (w.vault / "Portfolio").iterdir())
        (rc, out, err), = finish([proc])
        check(rc == 3 and out == "" and "records: repo" in err,
              f"an entry added meanwhile with `records: repo` makes the run unmanaged "
              f"(rc={rc}: {out!r} {err[:160]})")
        check(sorted(p.name for p in (w.vault / "Portfolio").iterdir()) == before
              and not (repo / ".claude").exists() and len(w.entries(repo)) == 1,
              "...and it creates no home and no sidecar, and appends nothing")


def case_sidecar_write_fails():
    print("--for-write when the sidecar cannot be written: a warning, exit 0, the home")
    td, w = world()
    with td:
        repo = w.repo()
        (repo / ".claude").mkdir()
        os.chmod(repo / ".claude", 0o555)
        try:
            r = w.run("--project", repo, "--for-write")
        finally:
            os.chmod(repo / ".claude", 0o755)
        home = w.vault / "Portfolio" / "apps" / "example-app"
        check(r.returncode == 0, f"exits 0 (rc={r.returncode}: {r.stderr.strip()[:200]})")
        check(one_line(r) == str(home), f"stdout is the home ({r.stdout!r})")
        check(home.is_dir(), "the home exists")
        check(len(w.entries(repo)) == 1, "the repo is registered")
        check("warning" in r.stderr and "PORTFOLIO-STATUS" in r.stderr
              and str(repo / ".claude" / "vault-context.md") in r.stderr
              and "Traceback" not in r.stderr,
              f"stderr warns that the sidecar block was not written, naming the file "
              f"({r.stderr.strip()[:240]!r})")
        check(not (repo / ".claude" / "vault-context.md").exists(), "no sidecar was written")


def case_help():
    print("--help states the whole first sentence and every mode")
    td, w = world()
    with td:
        r = w.run("--help")
        text = " ".join(r.stdout.split())
        check(r.returncode == 0 and "the resolver side of the records-resolver contract."
              in text, f"the description is a whole sentence ({text[:220]!r})")
        check(all(f in text for f in ("--for-write", "--decision-registers", "--all-homes")),
              "every mode is listed")
        check("Exit 0" in text and "Exit 3" in text and "Exit 2" in text,
              "the exit codes are listed")


# --------------------------------------------------------------------------
# --all-homes
# --------------------------------------------------------------------------
def case_all_homes():
    print("--all-homes: every entry's home, by the single-project rules, read-only")
    td, w = world()
    with td:
        app = w.repo(name="example-app")
        lib = w.repo(name="example-lib")
        off = w.repo(area="tools", name="example-off")
        w.register({"path": app, "name": "example-app", "area": "apps", "enabled": "true"},
                   {"path": lib, "name": "example-lib", "area": "apps", "enabled": "true",
                    "records": "repo"},
                   {"path": off, "name": "example-off", "area": "tools", "enabled": "false"})
        before = w.digest()
        r = w.run("--all-homes")
        check(r.returncode == 0, f"exits 0 (rc={r.returncode}: {r.stderr.strip()[:200]})")
        try:
            doc = json.loads(r.stdout)
        except ValueError:
            doc = {}
        print("    output: " + r.stdout.strip().replace("\n", "\n    "))
        p = f"{w.vault}/Portfolio"
        want = {"vault": str(w.vault), "projects": [
            {"name": "example-app", "area": "apps", "path": str(app), "enabled": True,
             "home": f"{p}/apps/example-app", "records": "vault", "reason": None},
            {"name": "example-lib", "area": "apps", "path": str(lib), "enabled": True,
             "home": None, "records": "repo", "reason": "OPT-OUT"},
            {"name": "example-off", "area": "tools", "path": str(off), "enabled": False,
             "home": f"{p}/tools/example-off", "records": "vault", "reason": None}]}
        got = json.loads(json.dumps(doc))
        for row in got.get("projects") or []:
            if row.get("reason") and "records: repo" in row["reason"]:
                row["reason"] = "OPT-OUT"
        check(got == want, f"the document is exactly the three rows ({doc})")
        check(w.digest() == before, "nothing is written")
        for repo, row in ((app, 0), (off, 2)):
            s = w.run("--project", repo)
            check(s.returncode == 0 and one_line(s) == want["projects"][row]["home"],
                  f"{repo.name}: the single-project mode prints the same home")
        s = w.run("--project", lib)
        check(s.returncode == 3, "example-lib: the single-project mode says unmanaged too")
        r = w.run("--all-homes", "--project", app)
        check(r.returncode == 2 and r.stdout == "",
              f"--all-homes takes no other argument: usage, exit 2 (rc={r.returncode})")
    td, w = world()
    with td:
        app = w.repo()
        w.register({"path": app, "name": "..", "area": "apps"},
                   {"path": w.repo(name="example-cli"), "name": "example-cli",
                    "area": "apps"})
        r = w.run("--all-homes")
        doc = json.loads(r.stdout) if r.returncode == 0 else {}
        rows = {row["name"]: row for row in doc.get("projects") or []}
        check(r.returncode == 0 and rows.get("..", {}).get("home") is None
              and "one folder name" in (rows.get("..", {}).get("reason") or "")
              and rows.get("example-cli", {}).get("home"),
              f"an entry the single mode refuses has no home and says why; the rest still "
              f"resolve (rc={r.returncode}: {rows})")
    td, w = world()
    with td:
        r = w.run("--all-homes")
        check(r.returncode == 0 and json.loads(r.stdout or "{}") ==
              {"vault": str(w.vault), "projects": []},
              f"no registry yet: exit 0 with no rows (rc={r.returncode}: {r.stdout!r})")
    td, w = world(vault=False, config=False)
    with td:
        app = w.repo()
        w.register({"path": app, "name": "example-app", "area": "apps"})
        before = w.digest()
        r = w.run("--all-homes")
        doc = json.loads(r.stdout) if r.stdout else {}
        check(r.returncode == 3 and "not configured" in r.stderr,
              f"no vault configured: exit 3, saying so (rc={r.returncode}: "
              f"{r.stderr.strip()[:160]})")
        check(doc.get("vault") is None and [(x["name"], x["home"]) for x in
                                           doc.get("projects") or []] == [("example-app", None)]
              and "not configured" in (doc["projects"][0].get("reason") or ""),
              f"...and stdout lists every entry with no home ({doc})")
        check(w.digest() == before, "...and writes nothing")
    for label, kw in (("config names a missing vault", dict(vault=False)),
                      ("vault without Portfolio/", dict(portfolio=False))):
        td, w = world(**kw)
        with td:
            before = w.digest()
            r = w.run("--all-homes")
            check(r.returncode == 2 and r.stdout == "" and "unreachable" in r.stderr,
                  f"{label}: exit 2, nothing on stdout (rc={r.returncode})")
            check(w.digest() == before, f"{label}: nothing is created")


def case_window_before_eligibility():
    print("a foreign window and a grouping folder together: the window is refused first")
    td, w = world()
    with td:
        repo = w.repo()
        w.register({"path": repo, "name": "example-app", "area": "apps", "enabled": "true"})
        protocol.start(w.vault.resolve(), owner="another-owner", purpose="test window",
                       lease_seconds=3600)
        before = w.digest()
        r = w.run("--project", repo.parent, "--for-write")
        check(r.returncode == 2 and "maintenance window" in r.stderr
              and "area directory" not in r.stderr,
              f"the refusal names the maintenance window, so the window is checked "
              f"before eligibility (rc={r.returncode}: {r.stderr.strip()[:120]})")
        check(w.digest() == before, "nothing is written")


# --------------------------------------------------------------------------
# --decision-registers
# --------------------------------------------------------------------------
def case_decision_registers():
    print("--decision-registers: exactly the existing registers for the inferred slugs")
    td, w = world()
    with td:
        dec = w.vault / "Portfolio/decisions"
        dec.mkdir()
        (dec / "rust.md").write_text("# rust\n", encoding="utf-8")
        (dec / "android.md").write_text("# android\n", encoding="utf-8")
        cargo = w.repo(name="example-crate", files=["Cargo.toml"])
        both = w.repo(name="example-both", files=["Cargo.toml", "settings.gradle"])
        bare = w.repo(name="example-bare")
        before = w.digest()
        r = w.run("--project", cargo, "--decision-registers")
        check(r.returncode == 0, f"a Cargo repo exits 0 (rc={r.returncode}: {r.stderr.strip()})")
        check(r.stdout == f"{dec / 'rust.md'}\n",
              f"...and prints only rust.md, not every register ({r.stdout!r})")
        r = w.run("--project", both, "--decision-registers")
        check(r.returncode == 0 and r.stdout == f"{dec / 'android.md'}\n{dec / 'rust.md'}\n",
              f"two matching slugs: both registers, sorted, one per line ({r.stdout!r})")
        r = w.run("--project", bare, "--decision-registers")
        check(r.returncode == 3 and r.stdout == "",
              f"no inferred domain: exits 3 with empty stdout, not 0 on an empty list "
              f"(rc={r.returncode}, {r.stdout!r})")
        (dec / "rust.md").unlink()
        r = w.run("--project", cargo, "--decision-registers")
        check(r.returncode == 3 and r.stdout == "",
              f"a slug whose register does not exist: exits 3 (rc={r.returncode}, "
              f"{r.stdout!r})")
        check(w.digest() != before, "(the register was removed, so the tree differs)")
        (dec / "rust.md").write_text("# rust\n", encoding="utf-8")
        check(w.digest() == before,
              "--decision-registers is read-only: with rust.md restored, the tree "
              "hashes as it did before the four runs")


def domain_entry(tag, links):
    gid = f"GDEC-{tag}-{1:03d}"  # built at run time: no literal id in the source
    applies = "".join(f"  - {link} (example)\n" for link in links)
    return (f"## {gid} — An example constraint\n\n- **Decided:** 2026-01-01\n"
            f"- **Status:** accepted\n- **Reason:** an example reason.\n"
            f"- **Applies to:**\n{applies}\n")


def case_decision_registers_applies_to():
    print("--decision-registers: a register that names the project under Applies to binds it")
    td, w = world()
    with td:
        dec = w.vault / "Portfolio/decisions"
        dec.mkdir()
        # No file signal infers `security`; the register's own link is the binding.
        (dec / "security.md").write_text(
            "# security\n\n---\n\n" + domain_entry("SEC", ["apps/[[example-bare]]"]),
            encoding="utf-8")
        # The same name in another area is another project.
        (dec / "web.md").write_text(
            "# web\n\n---\n\n" + domain_entry("WEB", ["tools/[[example-bare]]"]),
            encoding="utf-8")
        (dec / "rust.md").write_text(
            "# rust\n\n---\n\n" + domain_entry("RUST", ["apps/[[example-crate]]"]),
            encoding="utf-8")
        bare = w.repo(name="example-bare")
        cargo = w.repo(name="example-crate", files=["Cargo.toml"])
        before = w.digest()
        r = w.run("--project", bare, "--decision-registers")
        check(r.returncode == 0 and r.stdout == f"{dec / 'security.md'}\n",
              f"a register linking apps/[[example-bare]] binds it with no file signal, and "
              f"a link in another area does not ({r.returncode}, {r.stdout!r})")
        r = w.run("--project", cargo, "--decision-registers")
        check(r.returncode == 0 and r.stdout == f"{dec / 'rust.md'}\n",
              f"inferred and linked at once: listed once ({r.returncode}, {r.stdout!r})")
        check(w.digest() == before, "the Applies-to lookup is read-only")


def main():
    for k in list(os.environ):
        if k.startswith(("OBSIDIAN_", "VAULT_CONTEXT_", "BUSINESS_")) or k in (
                "XDG_CONFIG_HOME", "STAGED_PLANNING_CONFIG"):
            os.environ.pop(k)
    check(SCRIPT.is_file(), f"{SCRIPT.name} exists beside tests/")
    if not SCRIPT.is_file():
        print(f"\nFAIL: {len(FAILURES)} check(s) failed")
        sys.exit(1)
    for case in (case_read_unregistered, case_read_registered, case_unconfigured,
                 case_underivable, case_opt_out, case_unreachable, case_unparseable,
                 case_for_write_fresh, case_for_write_grouping_folder,
                 case_for_write_foreign_window, case_for_write_broken_integration,
                 case_relative_project,
                 case_registry_shapes, case_concurrent_register,
                 case_register_race_effective_entry, case_sidecar_write_fails,
                 case_window_before_eligibility, case_decision_registers,
                 case_decision_registers_applies_to, case_help,
                 case_all_homes):
        case()
    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed")
        sys.exit(1)
    print("OK — records-home answers the contract")


if __name__ == "__main__":
    main()
