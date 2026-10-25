#!/usr/bin/env python3
"""Every vault writer in vault-portfolio refuses a foreign maintenance window.

obsidian-wiki's maintenance protocol (the mirrored scripts/lib/vault_write_protocol.py)
lets one owner hold an exclusive window on a vault several hosts sync. A writer participates by
calling require_write_access() before it writes; one that skips the call writes into
a vault someone else is maintaining, and nothing else would notice.

The set of writers is FOUND, not listed. Every script under the plugin's core/ whose
--help offers a write mode (--write, --apply, --for-write, --fix, --restore) is run
in that mode against a synthetic vault, four times:

  control   no window: the run exits 0 and changes the vault, a repo or the registry. This is what
            makes the refusal below mean something; a mode that writes nothing here
            would pass the refusal checks without ever reaching a write.
  foreign   another owner's live window: non-zero exit, the protocol's refusal on
            stderr, and the vault, every repo and the registry byte-identical to before.
  expired   a window past its lease: refused the same way (a stale window needs an
            explicit recovery, never a silent takeover).
  owner     the window's own token in OBSIDIAN_WIKI_MAINTENANCE_TOKEN: exits 0, so
            the refusal comes from the protocol, not from refusing everything.

A writer that needs more than its flag to reach a write gets an entry in ARGV_HINTS.
A new writer without one fails its control run, which says what to add.

--help is not trusted to be the whole story, two ways:

  * a script whose --help exits non-zero or times out is a FAILURE, not a script
    with no write modes — otherwise a broken --help hides a writer;
  * a static pass reads each script's AST: one that calls a file-write primitive
    must also call require_write()/require_write_access(), or appear in
    READ_ONLY_ALLOWLIST below with its reason. A writer that offers no write flag
    is caught here even though the --help enumeration never runs it.

Throwaway HOME and temp vaults only. Stdlib + PyYAML, no pytest. Run:
  python3 -I src/vault-portfolio/core/skills/portfolio/tests/test-maintenance-participation.py
"""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
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
FIXTURES = HERE / "fixtures"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_config = _load(HERE.parent / "scripts" / "_config.py", "_maint_test_config")
CORE = _config.PLUGIN_ROOT
protocol = _load(CORE / "scripts" / "lib" / "vault_write_protocol.py", "_maint_test_protocol")

WRITE_FLAG_RE = re.compile(r"(?<![\w-])--(write|apply|for-write|fix|restore)(?![\w-])")
REFUSAL = "maintenance window"
RUN_ID = "RUN-TEST-1"

# Extra argv a writer needs to reach its writes, keyed by script name and flag.
ARGV_HINTS = {
    "portfolio-migrate.py": {"--write": ["--write", "--all"]},
    "plan-status-audit.py": {"--fix": ["--fix"], "--restore": ["--restore", RUN_ID]},
    # --write applies a --promote; the world's example-app register holds the entry.
    "domain-decisions.py": {"--write": ["--write", "--promote", "DEC" + "-001", "--area", "apps",
                                        "--name", "example-app", "--domain", "systems",
                                        "--reason", "every desktop tool shares this choice"]},
    # --for-write needs the repo it registers; the world's example-app is registered, so
    # the control run writes its sidecar block. Relative: run_writer's cwd is the world.
    "records-home.py": {"--for-write": ["--for-write", "--project", "repos/example-app"]},
    # --write applies a registry edit; removing the registered example-cli is one. The
    # world's temp root is too shallow to be a derived projects root, so it is named.
    "portfolio-scan.py": {"--write": ["--write", "--root", "repos", "--remove",
                                      "repos/example-cli"]},
}
# What a writer reads on stdin. --fix asks per plan; answering yes is what lets the
# control run write, so the refusal runs prove a "yes" is not enough.
STDIN = {"plan-status-audit.py": "y\n" * 20}

FAILURES: list[str] = []


def check(ok, msg):
    print(f"  {'ok' if ok else 'FAIL'}: {msg}")
    if not ok:
        FAILURES.append(msg)


def expand_ids(root: Path):
    for p in root.rglob("*.md"):
        t = p.read_text(encoding="utf-8")
        p.write_text(t.replace("{DEC}", "DEC").replace("{GDEC}", "GDEC").replace("{BL}", "BL"),
                     encoding="utf-8")


def base_env(home: Path) -> dict:
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
    return env


# --------------------------------------------------------------------------
# Enumeration
# --------------------------------------------------------------------------
def candidate_scripts():
    out = []
    for p in sorted(CORE.rglob("*")):
        rel = p.relative_to(CORE).as_posix()
        if not p.is_file() or p.suffix not in (".py", ".sh"):
            continue
        if "/tests/" in f"/{rel}" or "__pycache__" in rel or rel.startswith("vendor/"):
            continue
        out.append(p)
    return out


HELP_TIMEOUT = 60


def write_modes(tmp: Path):
    """([(script, flag)] for every script whose --help offers a write flag,
    [(script, why)] for every script whose --help failed or timed out)."""
    home = tmp / "help-home"
    home.mkdir(exist_ok=True)
    found, broken = [], []
    for script in candidate_scripts():
        cmd = ([sys.executable, "-I", str(script), "--help"] if script.suffix == ".py"
               else ["bash", str(script), "--help"])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=HELP_TIMEOUT,
                               env=base_env(home), cwd=tmp, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            broken.append((script, f"--help timed out after {HELP_TIMEOUT}s"))
            continue
        text = r.stdout + r.stderr
        if r.returncode != 0:
            last = text.strip().splitlines()[-1:] or ["no output"]
            broken.append((script, f"--help exited {r.returncode}: {last[0][:160]}"))
            continue
        for flag in sorted({f"--{m}" for m in WRITE_FLAG_RE.findall(text)}):
            found.append((script, flag))
    return found, broken


# --------------------------------------------------------------------------
# Static pass: a script that can write must take part in the protocol.
# --------------------------------------------------------------------------
# Scripts that call a write primitive yet legitimately never write the vault or a
# repo, each with its reason. Empty today: every script that can write calls
# require_write. An entry here is a claim a reviewer must be able to check.
READ_ONLY_ALLOWLIST: dict[str, str] = {}

PROTOCOL_CALLS = {"require_write", "require_write_access"}
# Method / function names that write, wherever they are called from.
WRITE_NAMES = {"write_text", "write_bytes", "atomic_write", "write_if_changed", "mkdir",
               "unlink", "rmdir", "touch", "rename", "symlink_to", "hardlink_to"}
# Names that only write when called on these modules (str.replace is not a write).
MODULE_WRITES = {
    "os": {"replace", "rename", "remove", "unlink", "rmdir", "removedirs", "makedirs",
           "mkdir", "symlink", "link", "truncate"},
    "shutil": {"copy", "copy2", "copyfile", "copytree", "copyfileobj", "move", "rmtree"},
}


def _call_name(node: ast.Call):
    """(module-ish base name or None, called name) for a call node."""
    fn = node.func
    if isinstance(fn, ast.Name):
        return None, fn.id
    if isinstance(fn, ast.Attribute):
        base = fn.value.id if isinstance(fn.value, ast.Name) else None
        return base, fn.attr
    return None, None


def _open_mode_writes(node: ast.Call, mode_pos: int) -> bool:
    """open()/fdopen() with a write mode. A mode that is not a literal is treated as
    a write: the check cannot prove it is read-only."""
    mode = node.args[mode_pos] if len(node.args) > mode_pos else None
    for kw in node.keywords:
        if kw.arg == "mode":
            mode = kw.value
    if mode is None:
        return False
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return any(c in mode.value for c in "wax+")
    return True


def write_calls(tree: ast.AST):
    """[(lineno, name)] of every file-write primitive called in `tree`."""
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        base, name = _call_name(node)
        if name is None:
            continue
        if base in MODULE_WRITES:
            if name in MODULE_WRITES[base]:
                hits.append((node.lineno, f"{base}.{name}"))
            continue
        if name in WRITE_NAMES:
            hits.append((node.lineno, name))
        elif name == "open" and _open_mode_writes(node, 1):
            hits.append((node.lineno, "open(w)"))
        elif name == "fdopen" and _open_mode_writes(node, 1):
            hits.append((node.lineno, "fdopen(w)"))
    return hits


def calls_protocol(tree: ast.AST) -> bool:
    return any(isinstance(n, ast.Call) and _call_name(n)[1] in PROTOCOL_CALLS
               for n in ast.walk(tree))


def static_candidates():
    """Scripts the static pass reads: candidate_scripts() minus scripts/lib/, which
    holds the protocol itself and byte-for-byte mirrors maintained elsewhere."""
    return [p for p in candidate_scripts()
            if not p.relative_to(CORE).as_posix().startswith("scripts/lib/")]


def static_cases():
    print("static pass — every script that can write calls the protocol:")
    rogue, unreadable, writers = [], [], []
    for script in static_candidates():
        rel = script.relative_to(CORE).as_posix()
        if script.suffix != ".py":
            # No AST to read: a shell script outside scripts/lib/ must be vouched for.
            if rel not in READ_ONLY_ALLOWLIST:
                unreadable.append(rel)
            continue
        try:
            tree = ast.parse(script.read_text(encoding="utf-8"), filename=rel)
        except (SyntaxError, UnicodeDecodeError) as e:
            unreadable.append(f"{rel} ({type(e).__name__})")
            continue
        hits = write_calls(tree)
        if not hits:
            continue
        writers.append(rel)
        if calls_protocol(tree) or rel in READ_ONLY_ALLOWLIST:
            continue
        rogue.append(f"{rel} ({', '.join(f'{n}@{ln}' for ln, n in hits[:4])})")
    print(f"  scripts with write primitives: {writers}")
    check(not unreadable, f"the static pass can read every script (unreadable: "
                          f"{unreadable or 'none'})")
    check(not rogue, f"every script that calls a write primitive calls require_write, or "
                     f"is in READ_ONLY_ALLOWLIST with a reason (rogue: {rogue or 'none'})")
    # An entry is stale when its script is gone, no longer writes, or now calls
    # the protocol: a leftover entry would excuse the next writer of that name.
    stale = [rel for rel in READ_ONLY_ALLOWLIST
             if not (CORE / rel).is_file() or rel not in writers
             or calls_protocol(ast.parse((CORE / rel).read_text(encoding="utf-8")))]
    check(not stale, f"every READ_ONLY_ALLOWLIST entry still names a script that needs it "
                     f"(stale: {stale or 'none'})")
    check(all(isinstance(v, str) and v.strip() for v in READ_ONLY_ALLOWLIST.values()),
          "every READ_ONLY_ALLOWLIST entry carries a reason")


# --------------------------------------------------------------------------
# Synthetic world: a vault, two repos, a registry and a config, per run.
# --------------------------------------------------------------------------
def build_world(tmp: Path):
    vault = tmp / "vault"
    port = vault / "Portfolio"
    home_dir = tmp / "home"
    repos = tmp / "repos"

    # example-app: already in the vault (plans, backlog, integration, a backup to restore).
    app_repo = repos / "example-app"
    (app_repo / ".claude").mkdir(parents=True)
    app_home = port / "apps" / "example-app"
    shutil.copytree(FIXTURES / "proj-a-plans-and-backlog" / "docs" / "plans", app_home / "plans")
    shutil.copy(FIXTURES / "proj-a-plans-and-backlog" / "docs" / "backlog.md",
                app_home / "backlog.md")
    (app_home / "plans" / "2026-01-05-finished-plan.md").write_text(
        "# Project Plan: finished\n\n### Task 1.1: one\n- **Status:** [x]\n", encoding="utf-8")
    backup = app_home / "plans" / ".audit-backups" / RUN_ID
    backup.mkdir(parents=True)
    (backup / "2026-01-05-finished-plan.md").write_text(
        "# Project Plan: finished (before)\n\n### Task 1.1: one\n- **Status:** [x]\n",
        encoding="utf-8")
    # A complete project decision with no Global: line, for a promotion to lift.
    (app_home / "decisions.md").write_text(
        "# Decisions\n\n---\n\n## {DEC}-001 — Config lives in one file\n\n"
        "- **Decided:** 2026-01-01\n- **Status:** accepted\n- **Domains:** systems\n"
        "- **Source:** direct\n- **Reason:** One file is one place to look.\n",
        encoding="utf-8")
    (app_home / "integration.md").write_text(
        "---\nproject: example-app\nimpacts:\n  - target: \"[[example-cli]]\"\n"
        "    why: the cli reads the app's export format\n---\n", encoding="utf-8")

    # example-cli: still in its repo, waiting to be migrated.
    cli_repo = repos / "example-cli"
    shutil.copytree(FIXTURES / "proj-b-plans-only", cli_repo)
    expand_ids(vault)
    expand_ids(repos)

    registry = tmp / "registry.yaml"
    registry.write_text(
        "projects:\n"
        f"  - name: example-app\n    area: apps\n    path: {app_repo}\n    enabled: true\n"
        f"  - name: example-cli\n    area: apps\n    path: {cli_repo}\n    enabled: true\n",
        encoding="utf-8")
    cfg = home_dir / ".config" / "obsidian-wiki" / "config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"default_vault": str(vault), "registry": str(registry)}),
                   encoding="utf-8")
    return vault, repos, home_dir, registry


def tree_hash(*roots: Path) -> str:
    h = hashlib.sha256()
    for root in roots:
        if root.is_file():  # a single file, such as the registry
            h.update(root.name.encode() + b"\0" + root.read_bytes() + b"\1")
            continue
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root.parent).as_posix()
            if "__pycache__" in rel:
                continue
            h.update(rel.encode() + b"\0")
            if p.is_file() and not p.is_symlink():
                h.update(p.read_bytes())
            h.update(b"\1")
    return h.hexdigest()


def foreign_window(vault: Path, expired=False) -> str:
    started = protocol.start(vault.resolve(), owner="another-owner", purpose="test window",
                             lease_seconds=3600)
    if expired:
        m = protocol.read_manifest(vault.resolve())
        past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
        m["started_at"] = protocol.as_timestamp(past - dt.timedelta(hours=1))
        m["expires_at"] = protocol.as_timestamp(past)
        protocol.write_json(protocol.manifest_path(vault.resolve()), m)
    return started["token"]


def run_writer(script: Path, flag: str, home: Path, tmp: Path, token=None):
    argv = ARGV_HINTS.get(script.name, {}).get(flag, [flag])
    cmd = ([sys.executable, "-I", str(script), *argv] if script.suffix == ".py"
           else ["bash", str(script), *argv])
    env = base_env(home)
    if token:
        env["OBSIDIAN_WIKI_MAINTENANCE_TOKEN"] = token
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env,
                          cwd=tmp, input=STDIN.get(script.name, ""))


def tail(r):
    lines = (r.stdout + r.stderr).strip().splitlines()
    return lines[-1] if lines else ""


def writer_cases(script: Path, flag: str):
    label = f"{script.relative_to(CORE).as_posix()} {flag}"
    print(f"{label}:")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        vault, repos, home, registry = build_world(tmp)
        before = tree_hash(vault, repos, registry)
        r = run_writer(script, flag, home, tmp)
        check(r.returncode == 0 and REFUSAL not in r.stderr,
              f"control (no window): exits 0 (rc={r.returncode}: {tail(r)})"
              + ("" if r.returncode == 0 else
                 f" — if this writer needs more argv, add it to ARGV_HINTS"))
        check(tree_hash(vault, repos, registry) != before,
              "control (no window): the run really writes in this mode (vault, repos or registry)")

    for kind in ("foreign", "expired"):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            vault, repos, home, registry = build_world(tmp)
            foreign_window(vault, expired=(kind == "expired"))
            before = tree_hash(vault, repos, registry)
            r = run_writer(script, flag, home, tmp)
            check(r.returncode != 0, f"{kind} window: exits non-zero (rc={r.returncode})")
            check(REFUSAL in r.stderr,
                  f"{kind} window: ...with the protocol's refusal, not another error "
                  f"({tail(r)})")
            check("Traceback (most recent call last)" not in r.stderr,
                  f"{kind} window: ...and no traceback")
            check(tree_hash(vault, repos, registry) == before,
                  f"{kind} window: the vault, the repos and the registry are byte-identical afterwards")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        vault, repos, home, registry = build_world(tmp)
        token = foreign_window(vault)
        r = run_writer(script, flag, home, tmp, token=token)
        check(r.returncode == 0 and REFUSAL not in r.stderr,
              f"owner's token: the window's own owner may write (rc={r.returncode}: {tail(r)})")


def main():
    for k in list(os.environ):
        if k.startswith(("OBSIDIAN_", "BUSINESS_", "VAULT_CONTEXT_")) or k in (
                "PORTFOLIO_CONFIG", "SECURITY_REGISTRY", "XDG_CONFIG_HOME"):
            os.environ.pop(k)
    with tempfile.TemporaryDirectory() as td:
        modes, broken = write_modes(Path(td))
    names = sorted({s.name for s, _ in modes})
    print(f"write modes found: {[f'{s.name} {f}' for s, f in modes]}")
    check(not broken, "every script's --help succeeds — a failing --help would hide its "
                      "write modes (" + ("; ".join(f"{s.relative_to(CORE).as_posix()}: {w}"
                                                    for s, w in broken) or "none") + ")")
    static_cases()
    # A floor, not the set: the enumeration must at least find the writers known to
    # exist, so an enumeration that silently finds nothing cannot pass.
    floor = {"portfolio-rebuild.py", "portfolio-unify.py", "portfolio-migrate.py",
             "portfolio-integrate.py", "plan-status-audit.py", "domain-decisions.py",
             "records-home.py", "portfolio-scan.py"}
    check(floor <= set(names),
          f"the --help enumeration finds every known writer (missing: "
          f"{sorted(floor - set(names)) or 'none'})")
    for script, flag in modes:
        writer_cases(script, flag)
    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed")
        sys.exit(1)
    print(f"OK — {len(modes)} write mode(s) across {len(names)} script(s) refuse a foreign window")


if __name__ == "__main__":
    main()
