"""Where vault-portfolio reads its configuration — the one definition every script imports.

  vault     1. $OBSIDIAN_VAULT_PATH — `~`-expanded and otherwise kept, even when it
               names a missing directory: a typo is reported against the path that
               was asked for (by the caller's reachability check), never silently
               replaced by a vault further down the list. A blank value is unset.
            2. ~/.config/obsidian-wiki/config.json `default_vault` — obsidian-wiki's
               own setting, read the same way resolve-vault.sh reads it, so levels 1
               and 2 name the vault obsidian-wiki uses
            3. ~/.claude/portfolio-config.yaml `vault_dir` — the legacy setting,
               which resolve-vault.sh does not read
            Nothing set: unconfigured (None). This deliberately differs from
            resolve-vault.sh, which falls back to ~/dev/knowledge: a script that
            writes into the vault never guesses which vault that is. Where the two
            differ is asserted by the marketplace's tests/test_vault_definitions.sh.

  registry  lib/registry_path.py, mirrored byte-for-byte from vault-context, so the
            two plugins cannot disagree about where the registry is. config.json is
            parsed here first, so a malformed file is refused rather than read past
            (the mirror on its own falls through, as vault-context's hooks must).

  business  $BUSINESS_SCAN_PATH (a scanner script, run with this interpreter), else
            config.json `business_scan` (an argv list, each item `~`-expanded).
            Neither: None, and the business layer is off. No other plugin is
            assumed to be installed.

A config.json or legacy file that is present but does not parse, or a key of the
wrong type, raises ConfigError: a deterministic script refuses an input shape it
does not parse rather than reading past it to a different vault. Only the value
of the setting is decided here; whether that vault is reachable is the caller's
one reachability check.

PLUGIN_ROOT is the nearest ancestor of this file that holds vendor/vendor.lock:
the plugin's own root, in the source tree and in the built plugin alike. The
search stops there and never looks further up. load_module() imports a file
under it (the vendored parser, the mirrored libs) by path.

Run as a script, it prints the resolved settings as JSON, or exits 2 with the
reason on stderr.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

VAULT_ENV = "OBSIDIAN_VAULT_PATH"
BUSINESS_ENV = "BUSINESS_SCAN_PATH"
OBSIDIAN_CONFIG = Path(".config") / "obsidian-wiki" / "config.json"
LEGACY_CONFIG = Path(".claude") / "portfolio-config.yaml"


class ConfigError(Exception):
    pass


def _find_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "vendor" / "vendor.lock").is_file():
            return parent
    raise ConfigError(f"no plugin root (vendor/vendor.lock) above {here}")


PLUGIN_ROOT = _find_root()


def load_module(relpath: str, name: str | None = None):
    """Import PLUGIN_ROOT/<relpath> by path and return the module."""
    path = PLUGIN_ROOT / relpath
    name = name or "_vault_portfolio_" + path.stem.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ConfigError(f"cannot load {relpath}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def home() -> Path:
    """A home directory, never an exception (HOME unset and no passwd entry)."""
    try:
        return Path.home()
    except Exception:
        return Path(os.environ.get("HOME") or "/nonexistent")


def _expand(value: str) -> Path:
    return home() / value[2:] if value.startswith("~/") else (home() if value == "~" else Path(value))


def obsidian_config_path() -> Path:
    return home() / OBSIDIAN_CONFIG


def legacy_config_path() -> Path:
    return home() / LEGACY_CONFIG


def obsidian_config() -> dict:
    """config.json as a dict; {} when absent. ConfigError when present but unparseable."""
    path = obsidian_config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ConfigError(f"{path} does not parse as JSON: {e}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path} is not a JSON object")
    return data


def _legacy_vault() -> str | None:
    path = legacy_config_path()
    if not path.is_file():
        return None
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except ImportError:
        raise ConfigError(f"reading {path} needs PyYAML, which is not installed") from None
    except Exception as e:
        raise ConfigError(f"{path} does not parse as YAML: {e}") from None
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ConfigError(f"{path} is not a YAML mapping")
    value = data.get("vault_dir")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{path}: vault_dir must be a string")
    return value.strip() or None


def vault_setting(env=None) -> tuple[Path | None, str | None]:
    """(vault, where it was set), or (None, None) when unconfigured."""
    env = os.environ if env is None else env
    value = (env.get(VAULT_ENV) or "").strip()
    if value:
        return _expand(value), VAULT_ENV
    cfg = obsidian_config()
    value = cfg.get("default_vault")
    if value is not None:
        if not isinstance(value, str):
            raise ConfigError(f"{obsidian_config_path()}: default_vault must be a string")
        if value.strip():
            return _expand(value.strip()), str(obsidian_config_path())
    value = _legacy_vault()
    if value:
        return _expand(value), str(legacy_config_path())
    return None, None


def registry_path() -> Path:
    """The registry file to read (may not exist), by the mirrored definition."""
    value = obsidian_config().get("registry")
    if value is not None and not isinstance(value, str):
        raise ConfigError(f"{obsidian_config_path()}: registry must be a string")
    return Path(load_module("scripts/lib/registry_path.py").registry_path())


def business_scan(env=None) -> list[str] | None:
    """The business scanner's argv, or None when the layer is off."""
    env = os.environ if env is None else env
    value = (env.get(BUSINESS_ENV) or "").strip()
    if value:
        return [sys.executable, str(_expand(value))]
    argv = obsidian_config().get("business_scan")
    if argv is None:
        return None
    if not (isinstance(argv, list) and argv and all(isinstance(a, str) and a for a in argv)):
        raise ConfigError(f"{obsidian_config_path()}: business_scan must be a non-empty "
                          "list of strings (an argv)")
    return [str(_expand(a)) if a.startswith("~") else a for a in argv]


if __name__ == "__main__":
    try:
        vault, source = vault_setting()
        doc = {"vault": str(vault) if vault else None, "vault_source": source,
               "registry": str(registry_path()), "business_scan": business_scan()}
    except ConfigError as e:
        print(f"vault-portfolio config: {e}", file=sys.stderr)
        sys.exit(2)
    json.dump(doc, sys.stdout)
    print()
