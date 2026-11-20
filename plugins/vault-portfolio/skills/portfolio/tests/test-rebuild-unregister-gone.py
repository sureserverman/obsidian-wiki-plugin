#!/usr/bin/env python3
"""rebuild unregisters a project whose folder is gone, and never creates a project folder.

Writing a sidecar into a registered path that no longer exists used to create the
folder, so the stale entry hid from scan's "registered but missing on disk" report.
Now, before the sidecars:

  * a registered path with nothing at it, whose nearest existing ancestor holds
    something, is gone: a dry run says `would unregister`, --write removes exactly
    that entry (scan's single-entry removal, every other byte kept);
  * a path under an EMPTY directory may be behind an unmounted mount point, and a
    dangling symlink may point at one: both stay registered;
  * no run, dry or --write, creates any of those folders;
  * a removal scan refuses (the registry's only entry) is a warning, not a crash,
    and still writes no sidecar.

Throwaway HOME, vault and projects only. Stdlib + PyYAML, no pytest. Run:
  python3 -I src/vault-portfolio/core/skills/portfolio/tests/test-rebuild-unregister-gone.py
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
SCRIPT = HERE.parent / "scripts" / "portfolio-rebuild.py"

failures: list[str] = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        failures.append(name)
        print(f"FAIL  {name}  {detail}")


T = Path(tempfile.mkdtemp(prefix="rebuild-gone-test-")).resolve()
HOME = T / "home"
VAULT = T / "vault"
DEV = T / "dev"
REG = T / "registry.yaml"
CONFIG = HOME / ".config" / "obsidian-wiki" / "config.json"


def env():
    return {"HOME": str(HOME), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}


def run(*args):
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, args)], env=env(),
                       capture_output=True, text=True, timeout=120, cwd="/")
    return r.returncode, r.stdout, r.stderr


def entry(path, name, area):
    return f"  - path: {path}\n    name: {name}\n    area: {area}\n    enabled: true\n"


try:
    (VAULT / "Portfolio").mkdir(parents=True)
    CONFIG.parent.mkdir(parents=True)
    CONFIG.write_text(json.dumps({"default_vault": str(VAULT), "registry": str(REG)}))

    alive = DEV / "apps" / "alive"
    (alive / ".git").mkdir(parents=True)
    gone = DEV / "apps" / "gone"                     # apps/ holds alive: really gone
    mount = T / "mnt" / "drive"                      # empty: looks unmounted
    mount.mkdir(parents=True)
    behind = mount / "proj"
    dangling = DEV / "apps" / "link"
    dangling.symlink_to(T / "nowhere" / "proj", target_is_directory=True)

    before = ("version: 1\n# the owner's projects\nprojects:\n"
              + entry(alive, "alive", "apps") + entry(gone, "gone", "apps")
              + entry(behind, "proj", "drive") + entry(dangling, "link", "apps"))
    REG.write_text(before)

    print("dry run:")
    rc, out, err = run()
    check("exit 0", rc == 0, f"rc={rc} {err}")
    check("names the gone project as would unregister",
          f"would unregister {gone} (apps/gone): folder gone" in out, out)
    check("names nothing else to unregister",
          out.count("unregister") == 1, out)
    check("the registry is untouched", REG.read_text() == before)
    check("no folder is created", not gone.exists() and not behind.exists()
          and not (T / "nowhere").exists())

    print("--write:")
    rc, out, err = run("--write")
    check("exit 0", rc == 0, f"rc={rc} {err}")
    check("says it unregistered the gone project",
          f"unregistered {gone} (apps/gone): folder gone" in out, out)
    want = before.replace(entry(gone, "gone", "apps"), "")
    check("exactly the gone entry's lines left the registry", REG.read_text() == want,
          REG.read_text())
    check("the entries that may be behind a mount stay registered",
          {p["name"] for p in yaml.safe_load(REG.read_text())["projects"]}
          == {"alive", "proj", "link"})
    check("no folder is created", not gone.exists() and not behind.exists()
          and not (T / "nowhere").exists())
    check("the mount-like and dangling entries are warned about, not written",
          str(behind) in err and str(dangling) in err and "Traceback" not in err, err)
    check("the live project still gets its sidecar",
          (alive / ".claude" / "vault-context.md").is_file())

    print("a gone project that is the registry's only entry:")
    REG.write_text("version: 1\nprojects:\n" + entry(gone, "gone", "apps"))
    only = REG.read_text()
    rc, out, err = run("--write")
    check("exit 0, no traceback", rc == 0 and "Traceback" not in err, f"rc={rc} {err}")
    check("the refusal is a warning naming the project",
          "could not be removed" in err and str(gone) in err, err)
    check("the registry is untouched", REG.read_text() == only)
    check("no folder is created", not gone.exists())
finally:
    shutil.rmtree(T, ignore_errors=True)

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("ALL OK")
