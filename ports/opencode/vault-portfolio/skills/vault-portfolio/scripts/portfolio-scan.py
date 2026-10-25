#!/usr/bin/env python3
"""portfolio-scan — walk the projects root, report registry drift, and apply the
single-entry registry edits the user names.

The walk is fixed: under each projects root, to a depth of four, a directory is
a project root when it holds any of
  docs/plans/                 (a real directory, not a symlink)
  docs/backlog.md             (a regular file)
  .claude/vault-context.md    (a regular file)
Symlinked directories are not descended into. Each hit's project root is the
parent of its `docs/` or `.claude/`, deduplicated by real path. Its `area` and
`name` are records-home.py's area_and_name(), the one derivation: the real path's
parent folder and last folder, as written. So an entry scan adds resolves, through
records-home, to the home records-home names for the same repo before it is
registered. A hit that IS the projects root, or whose folders are not one folder
name each, is listed as not addable.

The projects roots are `--root` when given (repeatable); otherwise the folder two
levels above each registered path (`<projects-root>/<area>/<name>`). A derived
root that is `/`, $HOME, or fewer than three folders deep is refused with "pass
--root" (exit 2): walking it would sweep a whole disk or home for projects. With
no registry and no `--root` there is nothing to walk, and the run says so (exit 2).

Drift is reported on every run, even when both lists are empty:
  found not in registry           walked project roots no entry names
  registered but missing on disk  entries whose path is not a directory
Disabled entries count as registered. Each found root is also checked against
the containment rule (the mirrored lib/eligibility.sh, through records-home.py),
so a grouping folder is marked not addable here rather than refused later.

Edits, all dry-run unless --write:
  --add PATH      append the entry for this found root (repeatable)
  --add-all       append every addable found root
  --remove PATH   remove this registered entry (repeatable)
Removals run first, then additions, each re-checked against the registry as it
stands. An addition is records-home.py's own register(): under the registry lock,
the containment check run again, the old bytes kept as a prefix, the result
parsed before it replaces the file; when another writer registered the repo
meanwhile, nothing is appended and that entry is reported. A removal takes out
exactly one entry's lines under the same lock and is checked the same way; a
comment or blank run just before the next entry belongs to that entry and stays.
A dry run makes every check a write would make, so a removal that would be
refused (the registry's only entry, say) is reported as refused. The file is
never rewritten whole; an edit that cannot be made that way is refused with the
entry to change by hand. A first addition creates the registry. --write needs a
configured, reachable vault and is refused while another owner holds its
maintenance window. --json reports drift only: with an edit flag it is a usage
error.

Exit codes: 0 report (and every requested edit done); 1 a requested edit was
refused, or the vault is unset or unreachable under --write; 2 usage (including
--json with an edit flag), a config file (config.json, or the legacy
portfolio-config.yaml) or registry that does not parse, a derived projects root
that is refused, or nothing to walk.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_cspec = importlib.util.spec_from_file_location("_vault_portfolio_config", _HERE / "_config.py")
_config = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(_config)

REBUILD = "skills/vault-portfolio/scripts/portfolio-rebuild.py"
RECORDS_HOME = "scripts/records-home.py"
MAX_DEPTH = 4
# rebuild owns the registry validator, the vault check and atomic_write; records-home
# owns the append, the registry lock and the containment check. Imported, not copied.
pr = _config.load_module(REBUILD)
rh = _config.load_module(RECORDS_HOME)
# A derived projects root needs at least this many folders below `/`.
MIN_ROOT_DEPTH = 3


class Refused(Exception):
    pass


def _depth(path, root):
    return len(path.relative_to(root).parts)


def walk(root):
    """Project roots under `root`, as {real path: walked path}."""
    found = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        depth = _depth(here, root)
        hits = []
        if here.name == "docs" and depth + 1 <= MAX_DEPTH:
            plans = here / "plans"
            if "plans" in dirnames and plans.is_dir() and not plans.is_symlink():
                hits.append(here.parent)
            backlog = here / "backlog.md"
            if "backlog.md" in filenames and backlog.is_file() and not backlog.is_symlink():
                hits.append(here.parent)
        if here.name == ".claude" and depth + 1 <= MAX_DEPTH:
            ctx = here / "vault-context.md"
            if "vault-context.md" in filenames and ctx.is_file() and not ctx.is_symlink():
                hits.append(here.parent)
        for hit in hits:
            found.setdefault(str(hit.resolve()), hit)
        if depth + 1 >= MAX_DEPTH:
            dirnames[:] = []
    return found


def candidate(real, walked, root, rh, registry):
    """One found project root: its entry fields and whether it may be added."""
    rel = walked.relative_to(root).parts
    entry = {"path": real, "root": str(root)}
    if not rel:
        entry.update(area=None, name=None, addable=False,
                     why="is the projects root itself, so it has no area")
        return entry
    try:
        area, name = rh.area_and_name(None, Path(real), registry)
    except rh.Exit as e:
        entry.update(area=None, name=None, addable=False, why=e.message.splitlines()[0])
        return entry
    entry.update(area=area, name=name)
    try:
        rh.require_eligible(Path(real), registry)
    except rh.Exit as e:
        entry.update(addable=False, why=e.message.splitlines()[0])
        return entry
    entry.update(addable=True, why=None)
    return entry


def roots_from(args, projects):
    if args.root:
        return [Path(r).expanduser().resolve() for r in args.root]
    home = _config.home().expanduser().resolve()
    seen = {}
    for p in projects:
        root = Path(p["path"]).expanduser().parent.parent
        real = root.resolve()
        why = ("the filesystem root" if real == Path(real.anchor) else
               "your home folder" if real == home else
               f"fewer than {MIN_ROOT_DEPTH} folders deep"
               if len(real.parts) - 1 < MIN_ROOT_DEPTH else None)
        if why:
            raise Refused(f"projects root {root}, derived from the registered path "
                          f"{p['path']}, is {why}; walking it would sweep far more than a "
                          f"projects folder — pass --root <projects-root>")
        seen.setdefault(str(root), root)
    return list(seen.values())


def drift(pr, rh, registry, projects, roots):
    registered = {str(Path(p["path"]).expanduser().resolve()) for p in projects}
    found = {}
    for root in roots:
        if not root.is_dir():
            raise Refused(f"projects root {root} is not a directory")
        for real, walked in walk(root).items():
            found.setdefault(real, (walked, root))
    new = [candidate(real, walked, root, rh, registry)
           for real, (walked, root) in sorted(found.items()) if real not in registered]
    missing = [{"path": p["path"], "area": p["area"], "name": p["name"]}
               for p in projects if not Path(p["path"]).expanduser().is_dir()]
    return new, missing


# --------------------------------------------------------------------------
# Removing one entry
# --------------------------------------------------------------------------
def _without(registry, target, wanted):
    """The registry's text with the one entry whose path is `wanted` taken out, every
    other byte kept, or Refused. Reads only; the caller holds the lock to write."""
    import yaml
    try:
        with open(target, encoding="utf-8", newline="") as fh:
            old = fh.read()
        old_data = yaml.safe_load(old)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
        raise Refused(f"registry {registry} could not be read: {e}")
    projects = old_data.get("projects") if isinstance(old_data, dict) else None
    if not isinstance(projects, list):
        raise Refused(f"registry {registry} has no `projects:` list")
    norm = str(Path(wanted).expanduser().resolve())
    keep = [p for p in projects
            if not (isinstance(p, dict) and isinstance(p.get("path"), str)
                    and str(Path(p["path"]).expanduser().resolve()) == norm)]
    if len(keep) == len(projects):
        raise Refused(f"not in registry: {wanted}")
    if len(projects) - len(keep) > 1:
        raise Refused(f"registry {registry} lists {wanted} more than once — remove the "
                      f"extra entries by hand")
    if not keep:
        raise Refused(f"it is the registry's only entry, and removing it would leave no "
                      f"`projects:` list — edit {registry} by hand")
    lines = old.splitlines(keepends=True)
    indent = rh._item_indent(old)
    starts = [i for i, line in enumerate(lines)
              if indent is not None and line.startswith(indent + "- ")]
    others = {k: v for k, v in old_data.items() if k != "projects"}
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        # A comment or blank run just before the next entry (or the end of the
        # file) is that entry's heading, or the file's tail, never this entry's.
        while end > start + 1 and (not lines[end - 1].strip()
                                   or lines[end - 1].lstrip().startswith("#")):
            end -= 1
        new = "".join(lines[:start] + lines[end:])
        try:
            data = yaml.safe_load(new)
        except yaml.YAMLError:
            continue
        if (isinstance(data, dict) and data.get("projects") == keep
                and {k: v for k, v in data.items() if k != "projects"} == others):
            return new
    raise Refused(f"registry {registry}: cannot remove the entry for {wanted} without "
                  f"rewriting the file — remove it by hand")


def _remove(pr, rh, registry, wanted, write):
    """Remove the one entry whose path is `wanted`, under the registry lock. A dry run
    (`write` false) makes the same checks and writes nothing."""
    target = registry.resolve() if registry.is_symlink() else registry
    if not write:
        _without(registry, target, wanted)
        return
    with rh.registry_lock(target):
        pr.atomic_write(target, _without(registry, target, wanted))


# --------------------------------------------------------------------------
def report(registry, exists, count, roots, new, missing, as_json):
    if as_json:
        json.dump({"registry": str(registry), "registry_exists": exists,
                   "registered": count, "roots": [str(r) for r in roots],
                   "found_not_in_registry": new,
                   "registered_but_missing_on_disk": missing}, sys.stdout, indent=1)
        print()
        return
    state = f"{count} entries" if exists else "absent — first run"
    print(f"registry: {registry} ({state})")
    print("projects roots: " + ", ".join(str(r) for r in roots))
    print(f"Drift — found not in registry: {len(new)} | "
          f"registered but missing on disk: {len(missing)}")
    for c in new:
        where = f"{c['area']}/{c['name']}" if c["area"] else "no area"
        print(f"  + {c['path']}  ({where})" + ("" if c["addable"] else
                                               f"  — not addable: {c['why']}"))
    for m in missing:
        print(f"  - {m['path']}  ({m['area']}/{m['name']})")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="portfolio-scan.py",
        description="Walk the projects root(s), report registry drift, and apply named "
                    "single-entry registry edits (dry-run unless --write).",
        epilog="Exit codes: 0 report and every requested edit done; 1 an edit refused, or "
               "an unset or unreachable vault under --write; 2 usage, config or registry "
               "that does not parse, or nothing to walk.")
    ap.add_argument("--root", action="append", default=[],
                    help="a projects root to walk (repeatable; default: derived from the registry)")
    ap.add_argument("--json", action="store_true", help="machine-readable drift report")
    ap.add_argument("--add", action="append", default=[], metavar="PATH",
                    help="append the entry for this found project root (repeatable)")
    ap.add_argument("--add-all", action="store_true", help="append every addable found root")
    ap.add_argument("--remove", action="append", default=[], metavar="PATH",
                    help="remove this registered entry (repeatable)")
    ap.add_argument("--write", action="store_true",
                    help="persist the edits (default: dry-run)")
    args = ap.parse_args(argv)
    if args.json and (args.add or args.add_all or args.remove):
        ap.error("--json reports drift only; it cannot be combined with --add, --add-all "
                 "or --remove")

    try:
        registry = _config.registry_path()
        # Read on every run: a config file that does not parse is exit 2 whether or
        # not this run writes, as the exit codes say. The vault is used only to write.
        setting, source = _config.vault_setting()
    except _config.ConfigError as e:
        print(f"vault-portfolio config: {e}", file=sys.stderr)
        return 2
    if args.write:
        # Before any read that could print a plan: a refused --write says only why.
        if setting is None:
            print(f"portfolio not configured: set {_config.VAULT_ENV}, or default_vault in "
                  f"{_config.obsidian_config_path()}", file=sys.stderr)
            return 1
        vault, problem = pr.vault_problem(setting, source)
        if problem:
            print(problem, file=sys.stderr)
            return 1
        pr.require_write(vault)
    exists = registry.exists()
    projects = pr.load_projects(enabled_only=False, path=registry, exit_code=2) if exists else []
    try:
        roots = roots_from(args, projects)
    except Refused as e:
        print(str(e), file=sys.stderr)
        return 2
    if not roots:
        print(f"nothing to walk: registry {registry} is absent or empty — pass "
              f"--root <projects-root> to seed it", file=sys.stderr)
        return 2
    try:
        new, missing = drift(pr, rh, registry, projects, roots)
    except Refused as e:
        print(str(e), file=sys.stderr)
        return 2
    report(registry, exists, len(projects), roots, new, missing, args.json)

    edits = bool(args.add or args.add_all or args.remove)
    if not edits:
        if args.write:
            print("--write with no --add, --add-all or --remove: nothing to write")
        return 0
    by_path = {c["path"]: c for c in new}
    adds, refused = [], []
    for wanted in args.add:
        real = str(Path(wanted).expanduser().resolve())
        c = by_path.get(real)
        if c is None:
            refused.append(f"--add {wanted}: not a found project root outside the registry")
        elif not c["addable"]:
            refused.append(f"--add {wanted}: not addable — {c['why']}")
        elif c not in adds:
            adds.append(c)
    if args.add_all:
        adds += [c for c in new if c["addable"] and c not in adds]
    removes = list(dict.fromkeys(args.remove))

    print("\nRegistry edits" + ("" if args.write else " (dry-run — pass --write to persist)") + ":")
    for wanted in removes:
        if not exists:
            refused.append(f"--remove {wanted}: not in registry")
            continue
        try:
            _remove(pr, rh, registry, wanted, args.write)
            print(f"  {'removed' if args.write else 'would remove'} {wanted}")
        except (Refused, OSError) as e:
            refused.append(f"--remove {wanted}: {e}")
    for c in adds:
        if not args.write:
            print(f"  would add {c['path']}  ({c['area']}/{c['name']})")
            continue
        repo = Path(c["path"])
        try:
            entry, appended = rh.register(
                pr, registry, repo, check=lambda _a, _n: rh.require_eligible(repo, registry))
            if appended:
                print(f"  added {c['path']}  ({entry['area']}/{entry['name']}, added "
                      f"{datetime.date.today().isoformat()})")
            else:
                print(f"  already registered {c['path']}  ({entry['area']}/{entry['name']}"
                      f"), by another writer since the walk; nothing appended")
        except rh.Exit as e:
            refused.append(f"--add {c['path']}: {e.message.splitlines()[0]}")
        except OSError as e:
            refused.append(f"--add {c['path']}: {e}")
    for line in refused:
        print(f"  REFUSED {line}")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
