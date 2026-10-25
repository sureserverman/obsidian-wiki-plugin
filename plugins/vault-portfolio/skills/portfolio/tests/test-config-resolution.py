#!/usr/bin/env python3
"""_config.py resolves the vault, the registry and the business scanner in one fixed order.

Every case runs `_config.py` as a subprocess in a throwaway HOME under a scrubbed
environment, so nothing here reads the machine's real config, vault or registry.

  vault     1. $OBSIDIAN_VAULT_PATH — used as given, never falling through, even
               when it names a missing directory (the caller's reachability check
               then reports it)
            2. ~/.config/obsidian-wiki/config.json `default_vault`
            3. ~/.claude/portfolio-config.yaml `vault_dir` (the legacy setting)
            none: unconfigured — never a guessed default
  registry  the mirrored lib/registry_path.py order
  business  $BUSINESS_SCAN_PATH, else config.json `business_scan` (an argv list)

Stdlib + PyYAML only, no pytest. Run:
  python3 src/vault-portfolio/core/skills/portfolio/tests/test-config-resolution.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "scripts" / "_config.py"
FAILS = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok: {label}")
    else:
        FAILS.append(label)
        print(f"FAIL: {label} {detail}", file=sys.stderr)


def run(home, **env):
    base = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    base.update({k: str(v) for k, v in env.items()})
    p = subprocess.run([sys.executable, "-I", str(CONFIG)], capture_output=True, text=True, env=base)
    data = json.loads(p.stdout) if p.returncode == 0 and p.stdout.strip() else None
    return p.returncode, data, p.stderr


def new_home(tmp, name):
    h = Path(tmp) / name
    (h / ".config" / "obsidian-wiki").mkdir(parents=True)
    (h / ".claude").mkdir()
    return h


def write_json(home, doc):
    (home / ".config" / "obsidian-wiki" / "config.json").write_text(
        doc if isinstance(doc, str) else json.dumps(doc))


def write_legacy(home, vault):
    (home / ".claude" / "portfolio-config.yaml").write_text(f"vault_dir: {vault}\n")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        vaults = {n: Path(tmp) / f"vault-{n}" for n in ("env", "json", "legacy")}
        for v in vaults.values():
            (v / "Portfolio").mkdir(parents=True)

        # --- each vault level, with every lower level present as a decoy -------
        h = new_home(tmp, "all-three")
        write_json(h, {"default_vault": str(vaults["json"])})
        write_legacy(h, vaults["legacy"])
        rc, d, err = run(h, OBSIDIAN_VAULT_PATH=vaults["env"])
        check("OBSIDIAN_VAULT_PATH wins over both config files",
              rc == 0 and d["vault"] == str(vaults["env"]) and d["vault_source"] == "OBSIDIAN_VAULT_PATH",
              f"rc={rc} {d} {err}")
        rc, d, err = run(h)
        check("config.json default_vault wins over the legacy setting",
              rc == 0 and d["vault"] == str(vaults["json"]) and d["vault_source"].endswith("config.json"),
              f"rc={rc} {d} {err}")
        h = new_home(tmp, "legacy-only")
        write_legacy(h, "~/../vault-legacy")
        rc, d, err = run(h)
        check("the legacy vault_dir is read when nothing else is set, ~ expanded",
              rc == 0 and Path(d["vault"]).resolve() == vaults["legacy"].resolve()
              and d["vault_source"].endswith("portfolio-config.yaml"), f"rc={rc} {d} {err}")

        # --- a missing env vault never falls through --------------------------
        h = new_home(tmp, "env-missing")
        write_json(h, {"default_vault": str(vaults["json"])})
        missing = Path(tmp) / "no-such-vault"
        rc, d, err = run(h, OBSIDIAN_VAULT_PATH=missing)
        check("OBSIDIAN_VAULT_PATH naming a missing directory is reported, not fallen through",
              rc == 0 and d["vault"] == str(missing) and d["vault_source"] == "OBSIDIAN_VAULT_PATH"
              and not missing.exists(), f"rc={rc} {d} {err}")

        # --- nothing configured: unconfigured, not a guessed default -----------
        h = new_home(tmp, "bare")
        (h / "dev" / "knowledge").mkdir(parents=True)
        rc, d, err = run(h)
        check("no vault setting is unconfigured, even with ~/dev/knowledge present",
              rc == 0 and d["vault"] is None and d["vault_source"] is None, f"rc={rc} {d} {err}")

        # --- a config.json this module cannot parse is refused ------------------
        h = new_home(tmp, "malformed")
        write_json(h, '{"default_vault": ')
        write_legacy(h, vaults["legacy"])
        rc, d, err = run(h)
        check("a malformed config.json is refused (exit 2), never read past",
              rc == 2 and "config.json" in err, f"rc={rc} {d} {err}")
        h = new_home(tmp, "wrong-type")
        write_json(h, {"default_vault": 7})
        rc, d, err = run(h)
        check("a default_vault that is not a string is refused (exit 2)", rc == 2, f"rc={rc} {d}")

        # --- the registry, one level at a time ----------------------------------
        h = new_home(tmp, "reg-key")
        write_json(h, {"registry": "~/named.yaml"})
        (h / ".claude" / "projects-registry.yaml").write_text("projects: []\n")
        rc, d, err = run(h)
        check("registry: the config.json key wins", rc == 0 and d["registry"] == str(h / "named.yaml"),
              f"{d} {err}")
        h = new_home(tmp, "reg-legacy")
        (h / ".claude" / "projects-registry.yaml").write_text("projects: []\n")
        rc, d, err = run(h)
        check("registry: the legacy file when it exists",
              rc == 0 and d["registry"] == str(h / ".claude" / "projects-registry.yaml"), f"{d} {err}")
        h = new_home(tmp, "reg-xdg")
        rc, d, err = run(h)
        check("registry: the obsidian-wiki XDG path otherwise",
              rc == 0 and d["registry"] == str(h / ".config" / "obsidian-wiki" / "projects-registry.yaml"),
              f"{d} {err}")

        # registry_path() on its own refuses what vault_setting() refuses: a script
        # that asks only for the registry must not read past a broken config.json.
        for name, doc in (("reg-malformed", '{"registry": '), ("reg-wrong-type", {"registry": 5})):
            h = new_home(tmp, name)
            write_json(h, doc)
            (h / ".claude" / "projects-registry.yaml").write_text("projects: []\n")
            p = subprocess.run(
                [sys.executable, "-I", "-c",
                 "import importlib.util,sys;"
                 f"s=importlib.util.spec_from_file_location('c', {str(CONFIG)!r});"
                 "c=importlib.util.module_from_spec(s);s.loader.exec_module(c);\n"
                 "try:\n    print(c.registry_path())\nexcept c.ConfigError as e:\n"
                 "    print('refused', e); sys.exit(2)"],
                capture_output=True, text=True, env={"HOME": str(h), "PATH": os.environ["PATH"]})
            check(f"registry_path() alone refuses a {name[4:]} config.json",
                  p.returncode == 2 and p.stdout.startswith("refused"), f"{p.returncode} {p.stdout}")

        # --- the business scanner ----------------------------------------------
        h = new_home(tmp, "business")
        write_json(h, {"business_scan": ["python3", "~/scan.py", "--all"]})
        rc, d, err = run(h)
        check("business_scan: the config.json argv list, ~ expanded",
              rc == 0 and d["business_scan"] == ["python3", str(h / "scan.py"), "--all"], f"{d} {err}")
        rc, d, err = run(h, BUSINESS_SCAN_PATH=Path(tmp) / "other-scan.py")
        check("business_scan: BUSINESS_SCAN_PATH overrides the config key",
              rc == 0 and d["business_scan"] == [sys.executable, str(Path(tmp) / "other-scan.py")],
              f"{d} {err}")
        rc, d, err = run(new_home(tmp, "no-business"))
        check("business_scan: none set is None (the layer is off)", rc == 0 and d["business_scan"] is None,
              f"{d} {err}")
        h = new_home(tmp, "business-bad")
        write_json(h, {"business_scan": "python3 scan.py"})
        rc, d, err = run(h)
        check("business_scan that is not a list of strings is refused (exit 2)", rc == 2, f"rc={rc} {d}")

    # --- the plugin root, and the vendored parser loaded from it ---------------
    p = subprocess.run([sys.executable, "-I", "-c",
                        "import importlib.util,sys;"
                        f"s=importlib.util.spec_from_file_location('c', {str(CONFIG)!r});"
                        "c=importlib.util.module_from_spec(s);s.loader.exec_module(c);"
                        "pp=c.load_module('vendor/staged_planning/plan_parser.py');"
                        "print(c.PLUGIN_ROOT, hasattr(pp, 'status_state'))"],
                       capture_output=True, text=True)
    words = p.stdout.split()
    root = Path(words[0]) if p.returncode == 0 and words else None
    check("PLUGIN_ROOT is the plugin's own root, and the vendored parser loads from it",
          root is not None and words[1:] == ["True"] and (root / "vendor" / "vendor.lock").is_file()
          and Path(__file__).resolve().relative_to(root).parts[:3] == ("skills", "portfolio", "tests"),
          f"{p.stdout} {p.stderr}")

    if FAILS:
        print(f"{len(FAILS)} failure(s)", file=sys.stderr)
        return 1
    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
