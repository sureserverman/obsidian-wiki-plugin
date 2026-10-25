#!/usr/bin/env python3
"""portfolio-migrate — move a project's docs into its vault home (copy→verify→delete).

Moves a project's operational docs from <repo>/docs/ into the vault at
<vault>/Portfolio/<area>/<name>/. The vault is not under version control, so
this is a filesystem copy with a sha256 verification gate, never git mv, never a
bare mv. The repo source is the LAST thing removed. --write is refused while
another owner holds the vault's maintenance window. An entry that sets
`records: repo` keeps its docs in the repo: --all skips it, and --project on it
is refused.

Usage:
  portfolio-migrate.py --project <project-root> [--write]
  portfolio-migrate.py --all [--write]
"""
import argparse, hashlib, importlib.util, re, shutil, subprocess, sys
from pathlib import Path

# portfolio-rebuild owns the vault, registry and write-access checks; nothing of
# them is restated here.
_spec = importlib.util.spec_from_file_location(
    "portfolio_rebuild", Path(__file__).resolve().parent / "portfolio-rebuild.py")
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def vault_dir():
    """The configured, reachable vault — portfolio-rebuild's one definition of it."""
    return pr.vault_dir()


def is_git(repo: Path) -> bool:
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
                       capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


def tracked_mods_in_set(repo: Path, rel_paths) -> list:
    """Return migrate-set files that are tracked AND have uncommitted modifications."""
    if not is_git(repo):
        return []
    out = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", "docs/"],
                         capture_output=True, text=True).stdout
    dirty = []
    for line in out.splitlines():
        code, _, path = line[:2], line[2], line[3:]
        # tracked modification/staged-add: ' M', 'MM', 'M ', 'A ', 'AM', 'R '
        if code.strip() and code not in ("??",):
            if any(path == rp or path.startswith(rp.rstrip("/") + "/") for rp in rel_paths):
                dirty.append(path)
    return dirty


def migrate_set(repo: Path):
    """Return list of (src_abs, rel_under_home) for files to migrate.

    Plans go to plans/. backlog.md and MATURITY.md go to the home root.
    A backlog.md stashed inside docs/plans/ (some projects keep it there
    because docs/plans/ is gitignored) is treated as THE backlog, not a
    plan — destination is <home>/backlog.md, provided no root docs/backlog.md
    exists. Never migrate a *-done.md historical summary as an active plan
    (it still moves, but stays under plans/ with its name).
    """
    items = []
    plans = repo / "docs" / "plans"
    root_backlog = repo / "docs" / "backlog.md"
    stray_backlog = plans / "backlog.md"
    if plans.is_dir():
        # recurse so nested plan groups (plans/<group>/*.md)
        # migrate too, preserving their subdir structure under the vault plans/.
        for f in sorted(plans.rglob("*.md")):
            if f.name == "backlog.md" and f.parent == plans:
                continue  # top-level stray backlog handled below, not a plan
            rel = f.relative_to(plans)
            items.append((f, f"plans/{rel.as_posix()}"))
    # backlog: prefer root docs/backlog.md; else a stray docs/plans/backlog.md
    if root_backlog.is_file():
        items.append((root_backlog, "backlog.md"))
    elif stray_backlog.is_file():
        items.append((stray_backlog, "backlog.md"))
    mat = repo / "docs" / "MATURITY.md"
    if mat.is_file():
        items.append((mat, "MATURITY.md"))
    return items


def resolve_home(vd: Path, area: str, name: str) -> Path:
    return vd / "Portfolio" / area / name


def migrate_project(proj, vd: Path, write: bool):
    repo = Path(proj["path"])
    home = resolve_home(vd, proj["area"], proj["name"])
    label = f"{proj['area']}/{proj['name']}"
    items = migrate_set(repo)
    if not items:
        return ("skip", label, "nothing to migrate (no plans/backlog/MATURITY)")

    # Preflight: vault home already populated?
    for sub in ("plans", "backlog.md", "MATURITY.md"):
        if (home / sub).exists():
            return ("skip", label, "vault home already populated; resolve manually")

    # Dirty-guard: tracked modifications only (use ACTUAL repo-relative source paths)
    src_relpaths = [str(src.relative_to(repo)) for src, _ in items]
    dirty = tracked_mods_in_set(repo, src_relpaths)
    if dirty:
        return ("skip", label, f"tracked uncommitted modifications: {', '.join(dirty)}")

    gitrepo = is_git(repo)
    flag = "" if gitrepo else " [no-git-fallback]"

    if not write:
        dests = ", ".join(rel for _, rel in items)
        return ("dry", label, f"{len(items)} files → {home}{flag}  ({dests})")

    # COPY. A ONE-TIME move, not a regenerate-in-place, so a changed-check has
    # nothing to compare against: once the repo docs/ has been emptied migrate_set()
    # returns nothing and the project is skipped before reaching here, and the
    # preflight above independently refuses an already-populated vault home. Those
    # two guards are what make a re-run a no-op. Note the ORDER — the emptied-docs
    # guard runs first and, on any real re-run, is the one that fires; the preflight
    # is reached only when docs/ has been repopulated. Both are exercised by the write-idempotency
    # test, the preflight by a case that repopulates docs/ on purpose, because
    # nothing else can reach it.
    # Re-check the sentinel at the WRITE, not only at resolve time: a mount that
    # drops after main()'s check would otherwise let the mkdir below rebuild the
    # whole chain from nothing and report a phantom vault as a successful migration.
    if not pr.vault_live(vd):
        return ("fail", label,
                "vault went away after the initial check — refusing to recreate it "
                "(mount dropped mid-run?). Nothing was written for this project.")
    (home / "plans").mkdir(parents=True, exist_ok=True)
    copied = []
    try:
        for src, rel in items:
            dest = home / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied.append((src, dest, rel))
        # VERIFY (load-bearing gate)
        for src, dest, rel in copied:
            if sha256(src) != sha256(dest):
                raise RuntimeError(f"sha256 mismatch on {rel}")
    except Exception as e:
        # abort: delete partial vault copies, leave repo untouched
        for _, dest, _ in copied:
            dest.unlink(missing_ok=True)
        return ("fail", label, f"{e} — repo left intact, partial vault copy removed")

    # DELETE from repo (last). Prefer `git rm` for tracked files so the
    # deletion is in git history (archaeology fallback); fall back to plain
    # rm for gitignored/untracked files (e.g. a gitignored docs/plans/) and
    # non-git repos — there the vault copy is the only copy.
    for src, _, rel in copied:
        removed = False
        if gitrepo:
            r = subprocess.run(["git", "-C", str(repo), "rm", "-q", "--", str(src.relative_to(repo))],
                               capture_output=True, text=True)
            removed = (r.returncode == 0)
        if not removed:
            src.unlink(missing_ok=True)
    # remove docs/plans if empty, then docs/ if empty
    pld = repo / "docs" / "plans"
    if pld.is_dir() and not any(pld.iterdir()):
        pld.rmdir()
    dd = repo / "docs"
    if dd.is_dir() and not any(dd.iterdir()):
        dd.rmdir()

    # step 7: record portfolio_home in the repo sidecar (create if absent)
    write_sidecar_home(repo, home)
    # step 8: rewrite migrated MATURITY.md auto-evidence with repo: prefix
    rewrite_maturity_evidence(home / "MATURITY.md")

    return ("ok", label, f"migrated {len(copied)} files → {home}{flag}")


# Rebuild's sentinels and splice, never restated: rebuild later rewrites this
# same block, so the two writers must agree on what marks it.
SIDECAR_BEGIN = pr.BEGIN
SIDECAR_END = pr.END


def write_sidecar_home(repo: Path, home: Path):
    """Ensure .claude/vault-context.md carries portfolio_home in the managed block.
    Creates a minimal sidecar if none exists. Idempotent. Full enrichment
    (counts/impacts/debt) happens later, in portfolio-rebuild."""
    sc = repo / ".claude" / "vault-context.md"
    sc.parent.mkdir(parents=True, exist_ok=True)
    block = (f"{SIDECAR_BEGIN}\n## Portfolio status\n\n"
             f"- **Home:** `{home}`   (plans/backlog/maturity live here, not in this repo's docs/)\n"
             f"{SIDECAR_END}")
    if sc.exists():
        cur = sc.read_text()
        new = pr.splice_sidecar(cur, block)
        # The equality check IS the write discipline here: write_if_changed adds
        # nothing but a `**Last rebuilt:**` strip, and this block carries no
        # timestamp to normalise (nor may it grow one). A second call with the
        # same home writes nothing — pinned by the write-idempotency test.
        if new != cur:
            sc.write_text(new)
    else:
        # Creation, not regeneration: reached only when no sidecar exists.
        sc.write_text(f"# Vault context for {repo.name}\n\n{block}\n")


# The scope prefixes an `auto:` tick may already carry (global-formats.md,
# "Evidence scope prefixes"). Only evidence that names NO tree is rewritten: a
# `portfolio:` tick points into the vault home, and adding `repo:` in front of it
# would point a reader at a repo file that does not exist.
EVIDENCE_SCOPES = ("repo", "portfolio")
UNSCOPED_EVIDENCE_RE = re.compile(
    r"^(\s*-\s*\[x\]\s*auto:)(?!(?:" + "|".join(EVIDENCE_SCOPES) + r"):)(.+)$")


def rewrite_maturity_evidence(mat: Path):
    """Rewrite `auto:<path>` → `auto:repo:<path>` for repo-relative evidence,
    so the vault checklist makes clear the evidence lives in the repo.
    Idempotent: skips lines that already carry a scope prefix (`repo:` or
    `portfolio:`)."""
    if not mat.is_file():
        return
    out = []
    changed = False
    for line in mat.read_text().splitlines():
        m = UNSCOPED_EVIDENCE_RE.match(line)
        if m:
            out.append(f"{m.group(1)}repo:{m.group(2)}")
            changed = True
        else:
            out.append(line)
    # Same discipline as write_sidecar_home: a line-level equality check, no
    # timestamp to strip, and a second pass over already-prefixed evidence
    # writes nothing. Pinned by the write-idempotency test.
    if changed:
        mat.write_text("\n".join(out) + "\n")


def main():
    ap = argparse.ArgumentParser(
        description="Move a project's plans, backlog and maturity checklist from its "
                    "repo's docs/ into its vault home (copy, verify, then delete). "
                    "Dry run unless --write.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--project", help="the registered project at this repo path")
    g.add_argument("--all", action="store_true", help="every enabled registered project")
    ap.add_argument("--write", action="store_true",
                    help="perform the move (refused while another owner holds the "
                         "vault's maintenance window)")
    args = ap.parse_args()

    vd = vault_dir()
    # An entry that keeps its records in its repo has no vault home to move into.
    if args.project:
        projects = pr.select_project(pr.load_projects(enabled_only=False), args.project,
                                     enabled_only=True, vault_only=True)
    else:
        projects = [p for p in pr.load_projects() if not pr.records_in_repo(p)]
    if args.write:
        pr.require_write(vd)

    counts = {"ok": 0, "dry": 0, "skip": 0, "fail": 0}
    for proj in projects:
        status, label, msg = migrate_project(proj, vd, args.write)
        counts[status] += 1
        print(f"[{status.upper():4}] {label}: {msg}")
    print(f"\n{'WRITE' if args.write else 'DRY-RUN'} summary: "
          f"migrated={counts['ok']} dry={counts['dry']} skipped={counts['skip']} failed={counts['fail']}")
    return 1 if counts["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
