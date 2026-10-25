#!/usr/bin/env python3
"""The security roll-up layer must be ADDITIVE, and a missing registry is never empty.

Mirrors test-business-degradation.py: taking the security scripts away must leave
the other roll-ups exactly as they were and must not fail the rebuild. A new
dashboard is never worth breaking the roll-ups the portfolio already depends on.

The other half is the failure the additivity rule could hide. A registry that is
not there is a fact the operator has to act on, not a portfolio with no projects:

  * security-scan.py, pointed at a missing registry (SECURITY_REGISTRY, or the
    default location when nothing names one), exits non-zero, names the file and
    prints no JSON — so no caller can render it.
  * portfolio-rebuild.py --write, whose scan fails that way, still exits 0 with
    the other roll-ups unchanged, says on stderr that the scan failed, and writes
    no global-security.md. Read as empty, the missing registry would instead
    write a dashboard that says nothing has been audited.
  * a roll-up that exits 0 but prints nothing usable (empty, blank, or without
    its heading) leaves an existing global-security.md byte-identical, says so on
    stderr, and is not reported written.

Each run gets its own throwaway HOME and synthetic vault under a scrubbed
environment. The "layer absent" run removes the security scripts from a copy of
the plugin tree, never from the source tree.

Run: python3 -I src/vault-portfolio/core/skills/portfolio/tests/test-security-degradation.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
SECURITY = ("security-scan.py", "security-rollup.py")


def plugin_root() -> Path:
    """The nearest ancestor holding vendor/vendor.lock, as _config.py finds it."""
    for parent in HERE.parents:
        if (parent / "vendor" / "vendor.lock").is_file():
            return parent
    raise SystemExit(f"FAIL: no plugin root (vendor/vendor.lock) above {HERE}")


def make_env(tmp: Path, **extra) -> tuple[dict, Path]:
    """A throwaway HOME + vault + registry; only HOME and PATH come from the caller."""
    home, vault = tmp / "home", tmp / "vault"
    (home / ".config" / "obsidian-wiki").mkdir(parents=True)
    (home / ".claude").mkdir()
    repo = tmp / "src" / "example-app"
    (repo / ".claude").mkdir(parents=True)
    (vault / "Portfolio" / "apps" / "example-app").mkdir(parents=True)
    reg = home / ".config" / "obsidian-wiki" / "projects-registry.yaml"
    reg.write_text("version: 1\nprojects:\n"
                   f"  - path: {repo}\n    name: example-app\n    area: apps\n"
                   "    enabled: true\n    added: 2026-01-01\n")
    (home / ".config" / "obsidian-wiki" / "config.json").write_text(
        json.dumps({"default_vault": str(vault), "registry": str(reg)}))
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    env.update({k: str(v) for k, v in extra.items()})
    return env, vault


def rebuild(scripts: Path, env: dict):
    p = subprocess.run([sys.executable, "-I", str(scripts / "portfolio-rebuild.py"), "--write"],
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stdout, p.stderr


def scan(env: dict):
    return subprocess.run([sys.executable, "-I", str(SCRIPTS / "security-scan.py")],
                          capture_output=True, text=True, env=env)


def others(out: str) -> list[str]:
    """What the rebuild reports about every roll-up except the security one."""
    return [seg.strip() for seg in out.split("|") if "security" not in seg]


def main() -> int:
    fails = []

    def chk(cond, msg):
        if not cond:
            fails.append(msg)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # --- layer present: the dashboard is written
        env_on, vault_on = make_env(tmp / "on")
        rc_on, out_on, err_on = rebuild(SCRIPTS, env_on)
        if rc_on != 0:
            print(f"FAIL: rebuild exited {rc_on} with the security layer present: "
                  f"{err_on.strip()[:300]}", file=sys.stderr)
            return 1
        chk("global-security written: True" in out_on,
            f"security layer not reported written when present: {out_on.strip()!r} "
            f"stderr={err_on.strip()[:300]!r}")
        chk((vault_on / "Portfolio" / "global-security.md").is_file(),
            "global-security.md not written with the layer present")

        # --- layer absent: removed from a copy of the plugin tree
        copy = tmp / "plugin-copy"
        root = plugin_root()
        shutil.copytree(root, copy, ignore=shutil.ignore_patterns("__pycache__", "fixtures"))
        copy_scripts = copy / SCRIPTS.relative_to(root)
        for name in SECURITY:
            (copy_scripts / name).unlink()
        env_off, vault_off = make_env(tmp / "off")
        rc_off, out_off, err_off = rebuild(copy_scripts, env_off)
        chk(rc_off == 0, f"rebuild exited {rc_off} with the security layer ABSENT — the "
                         f"layer must be optional: {err_off.strip()[:300]!r}")
        chk("security layer: unavailable" in out_off,
            f"absent layer not reported clearly: {out_off.strip()!r}")
        chk(not (vault_off / "Portfolio" / "global-security.md").exists(),
            "global-security.md written with the layer absent")
        chk(others(out_on) == others(out_off),
            f"other roll-ups changed when the security layer toggled:\n"
            f"  on : {others(out_on)}\n  off: {others(out_off)}")

        # --- SECURITY_REGISTRY names a missing file: the scan refuses, loudly
        missing = tmp / "nowhere" / "projects-registry.yaml"
        env_m, _ = make_env(tmp / "scan-missing", SECURITY_REGISTRY=missing)
        p = scan(env_m)
        chk(p.returncode != 0,
            f"scan exited 0 with SECURITY_REGISTRY at a missing file — a missing registry "
            f"was read as an empty one: stdout={p.stdout[:200]!r}")
        chk(str(missing) in p.stderr and "not found" in p.stderr,
            f"scan must name the missing registry on stderr: {p.stderr.strip()[:300]!r}")
        chk(not p.stdout.strip(),
            f"scan printed output for a missing registry, which a caller would render: "
            f"{p.stdout[:200]!r}")

        # --- nothing names a registry and the default file is absent: same refusal
        env_d, _ = make_env(tmp / "scan-default")
        cfg = Path(env_d["HOME"]) / ".config" / "obsidian-wiki" / "config.json"
        doc = json.loads(cfg.read_text())
        del doc["registry"]
        cfg.write_text(json.dumps(doc))
        (Path(env_d["HOME"]) / ".config" / "obsidian-wiki" / "projects-registry.yaml").unlink()
        p = scan(env_d)
        chk(p.returncode != 0 and "not found" in p.stderr and not p.stdout.strip(),
            f"scan with no registry anywhere must refuse, not report an empty portfolio: "
            f"rc={p.returncode} stdout={p.stdout[:200]!r} stderr={p.stderr.strip()[:300]!r}")

        # --- the rebuild degrades loudly around that refusal and writes no dashboard
        env_r, vault_r = make_env(tmp / "rebuild-missing", SECURITY_REGISTRY=missing)
        rc_r, out_r, err_r = rebuild(SCRIPTS, env_r)
        chk(rc_r == 0, f"a failed security scan failed the rebuild (rc={rc_r}): "
                       f"{err_r.strip()[:300]!r}")
        chk("global-security written" not in out_r,
            f"rebuild reported a security dashboard from a missing registry: {out_r.strip()!r}")
        chk("security-scan failed" in err_r and str(missing) in err_r,
            f"rebuild must say on stderr that the scan failed and why: {err_r.strip()[:300]!r}")
        chk(not (vault_r / "Portfolio" / "global-security.md").exists(),
            "global-security.md written from a missing registry")
        chk(others(out_on) == others(out_r),
            f"other roll-ups changed when the security scan failed:\n"
            f"  on    : {others(out_on)}\n  failed: {others(out_r)}")

        # --- a roll-up that exits 0 with nothing usable leaves the dashboard alone.
        # Run from a copy of the plugin tree whose security-rollup.py is a stub, never
        # by editing the source tree.
        previous = "# Global security\n\n- the previous good dashboard\n"
        stubs = {
            "empty stdout": "import sys\nsys.stdin.read()\n",
            "blank stdout": "import sys\nsys.stdin.read()\nprint('\\n   \\n')\n",
            "no dashboard heading": "import sys\nsys.stdin.read()\nprint('half a table')\n",
        }
        for label, stub in stubs.items():
            tag = label.replace(" ", "-")
            stub_copy = tmp / f"plugin-stub-{tag}"
            shutil.copytree(plugin_root(), stub_copy,
                            ignore=shutil.ignore_patterns("__pycache__", "fixtures"))
            stub_scripts = stub_copy / SCRIPTS.relative_to(plugin_root())
            (stub_scripts / "security-rollup.py").write_text(stub)
            env_s, vault_s = make_env(tmp / f"stub-{tag}")
            dash = vault_s / "Portfolio" / "global-security.md"
            dash.write_text(previous)
            before = dash.read_bytes()
            rc_s, out_s, err_s = rebuild(stub_scripts, env_s)
            chk(rc_s == 0, f"{label} roll-up failed the rebuild (rc={rc_s}): {err_s.strip()[:300]!r}")
            chk(dash.read_bytes() == before,
                f"{label} roll-up: the existing global-security.md was rewritten")
            chk("global-security written" not in out_s,
                f"{label} roll-up: reported as written, not failed: {out_s.strip()!r}")
            chk("global-security.md" in err_s and "untouched" in err_s,
                f"{label} roll-up: stderr does not say the dashboard was left untouched: "
                f"{err_s.strip()[-300:]!r}")

    if fails:
        print("FAILURES:", file=sys.stderr)
        for f in fails:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("OK — security layer is additive: rebuild succeeds without it, the other "
          "roll-ups are unchanged either way, and a missing registry is refused loudly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
