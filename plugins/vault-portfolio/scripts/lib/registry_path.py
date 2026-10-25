#!/usr/bin/env python3
"""registry_path.py — where the portfolio registry lives, defined once.

Run it and it prints one path. Import it and call `registry_path()`.

Resolution order:
  1. the `registry` key in ~/.config/obsidian-wiki/config.json
  2. ~/.claude/projects-registry.yaml, if it exists (the legacy location)
  3. ~/.config/obsidian-wiki/projects-registry.yaml

Level 1 is taken as given (with `~` expanded), whether or not the file exists:
the user named it, and readers already treat an absent registry as "nothing is
registered". Level 3 is the default, printed even when absent, for the same
reason.

A missing, unreadable or malformed config.json, or a `registry` value that is
not a non-empty string, falls through to level 2. That matches how
resolve-vault.sh treats the same file for `default_vault`: both read one
config, so they must agree on when it counts as unset.

Stdlib only.
"""

import json
import os
from pathlib import Path

LEGACY = Path(".claude") / "projects-registry.yaml"
XDG_DIR = Path(".config") / "obsidian-wiki"


def _config_registry(home: Path):
    """The config.json `registry` value, tilde-expanded, or None if unset."""
    try:
        with open(home / XDG_DIR / "config.json", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("registry")
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if value == "~" or value.startswith("~/"):
        value = str(home) + value[1:]
    return value


def registry_path() -> str:
    """Return the registry path per the resolution order above."""
    home = Path.home()
    configured = _config_registry(home)
    if configured is not None:
        return configured
    legacy = home / LEGACY
    if legacy.is_file():
        return str(legacy)
    return str(home / XDG_DIR / "projects-registry.yaml")


if __name__ == "__main__":
    print(registry_path())
