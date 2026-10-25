#!/usr/bin/env python3
"""records-home — where a project's records live in the vault: the resolver side of
the records-resolver contract.

planning asks one question: where do this project's plans, backlog, decisions and
maturity checklist live? Configured as planning's `records_resolver`, this script
answers it from the vault and the project registry. The answer is an exit code:

  0  stdout is exactly one absolute line, <vault>/Portfolio/<area>/<name>.
     Area and name come from the project's registry entry, else from the repo
     path: the parent folder is the area and the last folder the name, as
     written (<projects-root>/<area>/<name>). portfolio-scan registers a found
     repo by this same derivation.
  3  this project is not managed here, and planning keeps its records in the
     repo. stderr says which of three reasons applies: no vault is configured;
     no area and name can be derived from the path; or the registry entry sets
     `records: repo`, the per-project opt-out a public project uses to keep its
     records beside its code. Every other script skips such an entry too
     (portfolio-rebuild's records_in_repo()), and the registry validator
     (load_projects()) refuses any other `records` value, here as exit 2.
  2  the vault is configured but unreachable (vault_problem() in
     portfolio-rebuild.py is the one definition of reachable), or an input does
     not parse (a broken registry is named as broken), or a write was refused.
     An answer this script cannot give honestly is exit 2, never a guess; and
     exit 2 is never "unmanaged", because a dropped mount handled like an
     unconfigured machine is how records end up in the wrong place.

Without --for-write it only reads. With --for-write, in this order, it:
  1. refuses while another owner holds the vault's maintenance window (the
     mirrored vault_write_protocol, through rebuild's require_write);
  2. takes the registry lock and looks the repo up again; when it has no entry,
     it refuses a grouping folder, by asking the mirrored lib/eligibility.sh
     (project_eligible, and area_directory_message for the refusal) against the
     same registry it is about to append to, then refuses when the home already
     holds an integration.md that rebuild's read_integration() cannot read
     (the sidecar written in step 4 renders its edge lines from that file), and
     only then appends the entry (path, name, area, enabled: true, added). An
     entry another writer added meanwhile is used as it stands, and the home is
     computed from it; if it sets `records: repo`, the run is exit 3 and
     creates nothing. A repo that already had an entry gets the same two checks;
  3. creates the home;
  4. refreshes the repo's PORTFOLIO-STATUS block with rebuild's sidecar writer,
     for this one project.
Every refusal up to the registry append is exit 2 and leaves everything as it
was. After the append, a home that cannot be created is exit 2 (the entry stays,
and a re-run creates the home). A sidecar block that cannot be written is a
warning on stderr and the run still exits 0 with the home: the block is a cache
of what the registry and the vault already say, and planning stops on exit 2.
The opt-out holds in this mode too: it creates and registers nothing.

--decision-registers prints the absolute path of every existing
<vault>/Portfolio/decisions/<domain>.md whose slug domain-decisions.py's
infer_domains() finds in the repo, or which names the repo's <area>/[[<name>]]
under an entry's Applies to, sorted, one per line, and exits 0. It exits 3
when none exists, when no vault is configured, or on the opt-out, and 2 when the
vault is unreachable or a register cannot be read. It only reads.

--all-homes takes no other argument and only reads. It prints one JSON document,
{"vault": <abs path or null>, "projects": [row, ...]}, one row per registry entry
in registry order, each {"name", "area", "path", "enabled", "home", "records",
"reason"}: `path` as the registry writes it, `enabled` a boolean, `records`
"repo" for the opt-out and "vault" otherwise, `home` the absolute home the
single-project mode prints for that repo or null, and `reason` why `home` is
null (else null). The rules are the single-project mode's: the opt-out, an entry
the single mode refuses (an area or name that is not one folder name, or a repo
listed twice with different values) and an unconfigured vault each give a null
home with the reason. Exit 0 with the document; exit 3 when no vault is
configured, with stderr saying so and the document on stdout ("vault": null,
every home null); exit 2, with nothing on stdout, for an unreachable vault, a
config file or registry that does not parse. No registry yet is exit 0 with no
rows.

--project names the repo. The contract's caller passes an absolute path; a
relative one is resolved against the working directory. Symlinks are resolved
too, so a repo reached through a link is looked up, and registered, by the real
path it points at.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import fcntl
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PROG = "records-home"
# The scripts/ folder sits directly under the plugin root in the source tree and in
# the built plugin alike; everything past _config.py is reached through its
# PLUGIN_ROOT and load_module().
_cspec = importlib.util.spec_from_file_location(
    "_vault_portfolio_config",
    Path(__file__).resolve().parent.parent / "skills" / "portfolio" / "scripts" / "_config.py")
_config = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(_config)

ELIGIBILITY = "scripts/lib/eligibility.sh"
REBUILD = "skills/portfolio/scripts/portfolio-rebuild.py"
DOMAINS = "skills/portfolio/scripts/domain-decisions.py"
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
ELIGIBILITY_TIMEOUT = 5
# Seconds to pause between reading the registry and replacing it. Only the tests
# set it, to hold two writers inside the append at once.
TEST_APPEND_DELAY_ENV = "VAULT_PORTFOLIO_TEST_APPEND_DELAY"


class Exit(Exception):
    """Stop with this code and stderr message (and, for --all-homes, stdout lines)."""

    def __init__(self, code, message, lines=()):
        super().__init__(message)
        self.code = code
        self.message = message
        self.lines = list(lines)


def unmanaged(why):
    return Exit(3, f"unmanaged: {why}")


def refused(why):
    return Exit(2, why)


# --------------------------------------------------------------------------
# What the registry says about this repo
# --------------------------------------------------------------------------
def registry_projects(pr, registry):
    """Every registry entry, [] when there is no registry yet, or exit 2 naming the
    registry as broken. An absent registry means nothing is registered yet, a
    first-class state. The checks are rebuild's registry_problem(), the one
    validator (it also refuses a `records` value other than `repo`)."""
    if not registry.exists():
        return []
    projects, why = pr.registry_problem(registry)
    if why:
        raise refused(f"registry {registry} is broken: {why}")
    return projects


def _norm(value):
    return Path(value).expanduser().resolve()


def conflict(pr, hits):
    """Why a repo's entries cannot be used together, or None."""
    shapes = {(h["area"], h["name"], h.get(pr.RECORDS_KEY)) for h in hits}
    if len(shapes) > 1:
        return (f"lists {hits[0]['path']} {len(hits)} times with different area, name or "
                f"{pr.RECORDS_KEY} values — fix the registry")
    return None


def registry_entry(pr, registry, repo):
    """The repo's registry entry (a dict), or None when it has none."""
    hits = [p for p in registry_projects(pr, registry) if _norm(p["path"]) == repo]
    if not hits:
        return None
    why = conflict(pr, hits)
    if why:
        raise refused(f"registry {registry} {why}")
    return hits[0]


def opt_out_exit(pr, repo):
    return unmanaged(f"the registry entry for {repo} sets `{pr.RECORDS_KEY}: "
                     f"{pr.RECORDS_IN_REPO}`, so its records stay in the repo")


def segment_ok(value):
    return (isinstance(value, str) and value not in ("", ".", "..") and "/" not in value
            and not CONTROL_RE.search(value) and value == value.strip())


def area_and_name(entry, repo, registry):
    if entry is not None:
        area, name = entry["area"], entry["name"]
        if not (segment_ok(area) and segment_ok(name)):
            raise refused(f"registry {registry}: area {area!r} / name {name!r} for {repo} "
                          f"must each be one folder name")
        return area, name
    parts = repo.parts[1:]  # without the root
    if len(parts) < 2 or not (segment_ok(parts[-2]) and segment_ok(parts[-1])):
        raise unmanaged(f"cannot derive an area and a name from {repo} — a repo path "
                        f"shaped like <projects-root>/<area>/<name> has both")
    return parts[-2], parts[-1]


# --------------------------------------------------------------------------
# --for-write
# --------------------------------------------------------------------------
def require_eligible(repo, registry):
    """The containment rule, asked of the mirrored eligibility.sh, never restated."""
    lib = _config.PLUGIN_ROOT / ELIGIBILITY
    env = dict(os.environ, VAULT_CONTEXT_REGISTRY=str(registry))
    script = ('source "$1" || exit 90; project_eligible "$2" && exit 0; '
              'area_directory_message "$2" >&2; exit 1')
    try:
        r = subprocess.run(["bash", "-c", script, PROG, str(lib), str(repo)], env=env,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=ELIGIBILITY_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        raise refused(f"the project check ({ELIGIBILITY}) could not run: {e}")
    if r.returncode == 0:
        return
    if r.returncode == 1 and r.stderr.strip():
        raise refused(r.stderr.rstrip("\n"))
    raise refused(f"the project check ({ELIGIBILITY}) failed (exit {r.returncode}): "
                  f"{r.stderr.strip()}")


def _entry_text(entry, indent):
    import yaml
    text = yaml.safe_dump([entry], sort_keys=False, default_flow_style=False,
                          allow_unicode=True, width=1 << 30)
    return "".join(indent + line for line in text.splitlines(keepends=True))


def _item_indent(text):
    """The indent of the first list item under `projects:`, or None."""
    m = re.search(r"^projects:[ \t]*(?:#[^\n]*)?\n(?:[ \t]*(?:#[^\n]*)?\n)*([ \t]*)- ",
                  text, re.M)
    return m.group(1) if m else None


@contextlib.contextmanager
def registry_lock(target):
    """An exclusive flock on the registry's folder, held from read to replace.

    The folder, not the file: the replace swaps the file for a new one, so a lock
    taken on the old file would no longer guard the registry. Locking the folder's
    descriptor creates no lock file beside the registry (flock on a directory works
    on Linux and macOS). Closing the descriptor releases it.
    """
    folder = target.parent
    folder.mkdir(parents=True, exist_ok=True)
    fd = os.open(folder, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _test_delay():
    try:
        delay = float(os.environ.get(TEST_APPEND_DELAY_ENV) or 0)
    except ValueError:
        delay = 0
    if 0 < delay <= 10:
        time.sleep(delay)


def register(pr, registry, repo, check=None):
    """(entry, appended): the repo's EFFECTIVE registry entry, appended under the
    registry lock when it has none.

    The entry is looked up again inside the lock: a run that waited for the lock
    finds the entry another writer just added, appends nothing, and returns that
    entry, so the caller computes the home from it rather than from the path.
    Otherwise area and name come from area_and_name(), the one derivation, and
    `check(area, name)` runs inside the lock before the append; an Exit it raises
    leaves the registry as it was.
    """
    target = registry.resolve() if registry.is_symlink() else registry
    with registry_lock(target):
        found = registry_entry(pr, registry, repo)
        if found is not None:
            return found, False
        area, name = area_and_name(None, repo, registry)
        if check is not None:
            check(area, name)
        return _append(pr, registry, target, repo, area, name), True


def _append(pr, registry, target, repo, area, name):
    """Appended, never rewritten: the old bytes stay a prefix of the new file, and
    the result is parsed and checked before it replaces the registry."""
    import yaml
    entry = {"path": str(repo), "name": name, "area": area, "enabled": True,
             "added": datetime.date.today()}
    nl = "\n"
    if target.exists():
        try:
            # newline="": the text exactly as stored, so a CRLF registry keeps its
            # line ends and stays a byte prefix of what is written back.
            with open(target, encoding="utf-8", newline="") as fh:
                old = fh.read()
            old_data = yaml.safe_load(old)
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
            raise refused(f"registry {registry} could not be read again to append: {e}")
        mode = target.stat().st_mode & 0o7777
        indents = [_item_indent(old), "  ", ""]
        if "\r\n" in old:
            nl = "\r\n"
        base = old if old == "" or old.endswith("\n") else old + nl
    else:
        old_data = {"version": 1, "projects": []}
        umask = os.umask(0)
        os.umask(umask)
        mode = 0o666 & ~umask
        indents = ["  "]
        base = "version: 1\n\nprojects:\n"
    _test_delay()
    if not isinstance(old_data, dict) or not isinstance(old_data.get("projects"), list):
        raise refused(f"registry {registry} has no `projects:` list to append to")
    for indent in dict.fromkeys(i for i in indents if i is not None):
        new = base + _entry_text(entry, indent).replace("\n", nl)
        try:
            data = yaml.safe_load(new)
        except yaml.YAMLError:
            continue
        if (isinstance(data, dict) and data.get("projects") == old_data["projects"] + [entry]
                and {k: v for k, v in data.items() if k != "projects"}
                == {k: v for k, v in old_data.items() if k != "projects"}):
            pr.atomic_write(target, new)
            os.chmod(target, mode)
            return entry
    raise refused(f"registry {registry}: cannot append an entry without rewriting the file "
                  f"(is `projects:` the last key, in block style?) — add this entry by hand:\n"
                  + _entry_text(entry, "  ").rstrip("\n"))


def home_of(vault, area, name):
    return vault / "Portfolio" / area / name


def for_write(pr, vault, registry, entry, repo):
    """Create the home and register the repo (module docstring, steps 1-4); the home."""
    try:
        pr.require_write(vault)
    except SystemExit as e:
        raise refused(e.code if isinstance(e.code, str) else "vault write refused")

    def preflight(area, name):
        require_eligible(repo, registry)
        if not pr.vault_live(vault):
            raise refused(f"vault unreachable: {vault / 'Portfolio'} went away — nothing "
                          f"created")
        # The sidecar written last renders its edge lines from the home's
        # integration.md. One that cannot be read is refused here, before the
        # registry append and the mkdir, so the refusal leaves nothing behind.
        integration = pr.integration_path(home_of(vault, area, name))
        if integration.exists():
            _fm, why = pr.read_integration(integration)
            if why:
                raise refused(f"{integration}: {why} — fix it (integration-format.md) and "
                              f"re-run; nothing created")

    # Registered before the home is created: a registry that refuses the append
    # then leaves nothing behind.
    appended = False
    if entry is None:
        entry, appended = register(pr, registry, repo, check=preflight)
    if pr.records_in_repo(entry):
        raise opt_out_exit(pr, repo)
    area, name = area_and_name(entry, repo, registry)
    if not appended:
        preflight(area, name)
    home = home_of(vault, area, name)
    try:
        home.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise refused(f"cannot create the records home {home} (the registry entry is "
                      f"in place): {e}")
    sidecar = Path(repo) / ".claude" / "vault-context.md"
    try:
        pr.write_sidecar(str(repo), home, vault, True)
    except (OSError, ValueError) as e:
        # A cache of what the registry and the vault already say: the home is real
        # and registered, so the answer stands (module docstring).
        print(f"{PROG}: warning: the home {home} and its registry entry are in place, but "
              f"the PORTFOLIO-STATUS block in {sidecar} could not be written ({e}); "
              f"/vault-portfolio rebuild --write refreshes it", file=sys.stderr)
    return home


# --------------------------------------------------------------------------
# --decision-registers
# --------------------------------------------------------------------------
def linked_registers(pr, folder, area, name):
    """Registers with an entry naming <area>/[[<name>]] under Applies to.

    A domain no file shows (security, say) reaches a project only this way: the
    register's own link, the edge the roll-up symmetry-checks, is the binding.
    """
    linked = set()
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else ():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise refused(f"cannot read the decision register {path}: {e}")
        for entry in pr.parse_decision_file(text, pr.GDEC_ID_RE, pr.DOMAIN_REQUIRED):
            links = pr.APPLIES_LINK_RE.findall(entry["fields"].get("Applies to", ""))
            if any(a == area and n.split("|")[0].strip() == name for a, n in links):
                linked.add(str(path))
                break
    return linked


def decision_registers(pr, vault, repo, entry, registry):
    domains = _config.load_module(DOMAINS)
    try:
        slugs = domains.infer_domains(repo)
    except (OSError, ValueError) as e:
        raise refused(f"cannot infer {repo}'s domains: {e}")
    folder = vault / domains.REGISTER_DIR
    found = {str(folder / f"{s}.md") for s in slugs if (folder / f"{s}.md").is_file()}
    try:
        area, name = area_and_name(entry, repo, registry)
    except Exit as e:
        if e.code != 3:
            raise
        area = name = None  # no area/name, so no register can link this repo
    if area is not None:
        found |= linked_registers(pr, folder, area, name)
    if not found:
        raise Exit(3, f"no per-domain decision register binds {repo} (domains inferred: "
                      f"{', '.join(slugs) or 'none'}; none links it under Applies to)")
    return sorted(found)


# --------------------------------------------------------------------------
def settings():
    try:
        setting, source = _config.vault_setting()
        registry = _config.registry_path()
    except _config.ConfigError as e:
        raise refused(f"vault-portfolio config: {e}")
    return setting, source, registry


def not_configured():
    return (f"the vault is not configured (set {_config.VAULT_ENV}, or default_vault in "
            f"{_config.obsidian_config_path()})")


def resolve(args):
    repo = Path(args.project).expanduser().resolve()
    setting, source, registry = settings()
    if setting is None:
        raise unmanaged(not_configured())
    pr = _config.load_module(REBUILD)
    entry = registry_entry(pr, registry, repo)
    if entry is not None and pr.records_in_repo(entry):
        raise opt_out_exit(pr, repo)
    vault, problem = pr.vault_problem(setting, source)
    if problem:
        raise refused(problem)
    if args.decision_registers:
        return decision_registers(pr, vault, repo, entry, registry)
    if args.for_write:
        return [str(for_write(pr, vault, registry, entry, repo))]
    return [str(home_of(vault, *area_and_name(entry, repo, registry)))]


# --------------------------------------------------------------------------
# --all-homes
# --------------------------------------------------------------------------
def all_homes():
    """The --all-homes document as one JSON line; see the module docstring."""
    setting, source, registry = settings()
    pr = _config.load_module(REBUILD)
    projects = registry_projects(pr, registry)
    vault, unset = None, None
    if setting is None:
        unset = not_configured()
    else:
        vault, problem = pr.vault_problem(setting, source)
        if problem:
            raise refused(problem)
    groups = {}
    for p in projects:
        groups.setdefault(_norm(p["path"]), []).append(p)
    rows = []
    for p in projects:
        repo = _norm(p["path"])
        row = {"name": p["name"], "area": p["area"], "path": p["path"],
               "enabled": pr.is_enabled(p), "home": None,
               "records": pr.RECORDS_IN_REPO if pr.records_in_repo(p) else "vault",
               "reason": None}
        if unset:
            row["reason"] = unset
        elif pr.records_in_repo(p):
            row["reason"] = pr.OPTED_OUT
        elif conflict(pr, groups[repo]):
            row["reason"] = f"the registry {conflict(pr, groups[repo])}"
        else:
            try:
                row["home"] = str(home_of(vault, *area_and_name(p, repo, registry)))
            except Exit as e:
                row["reason"] = e.message
        rows.append(row)
    doc = json.dumps({"vault": str(vault) if vault else None, "projects": rows})
    if unset:
        raise Exit(3, unset, [doc])
    return [doc]


DESCRIPTION = ("Print where a project's records live in the vault: the resolver side of "
               "the records-resolver contract.")
EPILOG = ("Exit 0: one absolute line on stdout (--all-homes: one JSON document). "
          "Exit 3: unmanaged, records stay in the repo (--all-homes: no vault is "
          "configured). Exit 2: unreachable, unparseable or refused; nothing on stdout.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog=PROG, description=DESCRIPTION, epilog=EPILOG)
    ap.add_argument("--project", help="the repo (an absolute path); required unless "
                                      "--all-homes")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--for-write", action="store_true",
                      help="create the home, register the repo and refresh its sidecar "
                           "block (refused while another owner holds the vault's "
                           "maintenance window)")
    mode.add_argument("--decision-registers", action="store_true",
                      help="list the per-domain decision registers that bind the repo")
    mode.add_argument("--all-homes", action="store_true",
                      help="print every registry entry's home as one JSON document "
                           "(read-only; takes no other argument)")
    args = ap.parse_args(argv)
    if args.all_homes and args.project is not None:
        ap.error("--all-homes takes no other argument")
    if not args.all_homes and args.project is None:
        ap.error("the following arguments are required: --project")
    try:
        lines = all_homes() if args.all_homes else resolve(args)
    except Exit as e:
        print(f"{PROG}: {e.message}", file=sys.stderr)
        sys.stdout.write("".join(line + "\n" for line in e.lines))
        return e.code
    except Exception as e:
        print(f"{PROG}: unexpected failure: {e!r}", file=sys.stderr)
        return 2
    sys.stdout.write("".join(line + "\n" for line in lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
