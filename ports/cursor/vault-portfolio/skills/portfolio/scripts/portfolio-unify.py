#!/usr/bin/env python3
"""portfolio-unify — backlog candidates from every registered project's vault plans.

Reads each project's plans from <vault>/Portfolio/<area>/<name>/plans/ through
the vendored plan parser, dedups against the existing <home>/backlog.md by exact
Source string, and (with --write) appends BL-NNN entries tagged `auto-unified`.
Dry run by default; --write is refused while another owner holds the vault's
maintenance window. An entry that sets `records: repo` has no vault plans: a run
skips it, and --project on it is refused.

Candidate signals (accept-all policy), all decided by the parser's parse_plan():
  - Status-authoritative tasks     (plans carrying `- **Status:**` fields: a task
                                     with `Status: [ ]` -> status-unexecuted;
                                     `[~]` -> status-partial; `[x]` -> nothing;
                                     stray body bullets ignored)
  - unchecked legacy tasks         (plans without Status fields: an unchecked
                                     `- [ ]` bullet in a stage that git evidence
                                     does not mark executed)
  - Deferred-section bullets       (## Deferred / ### Deferred blocks, in BOTH
                                     modes; an explicit parking register)
Excluded: Preflight bullets, stage-gate bullets (acceptance criteria, not
deferred work), every file portfolio-rebuild's not_a_plan() names (README.md,
backlog.md, and *-design.md, *-architecture.md and *-done.md documents, the same
files compass skips), and stale-plan items unless --include-stale
(staleness comes from the filename YYYY-MM-DD stamp, since the vault has no
history and mtimes are rewritten by moves).

An `**Abandoned:**` plan still contributes its open tasks: they are proposed for
human triage, and suppressing them would hide work from the one view that lists it.
"""
import argparse, importlib.util, re, subprocess, sys, datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, _HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# portfolio-rebuild owns the vault, registry and write-access checks; the plan
# format has one definition, the vendored parser. Nothing of either is restated here.
pr = _load("portfolio_rebuild", "portfolio-rebuild.py")
plan_parser = pr._config.load_module("vendor/staged_planning/plan_parser.py")
STATUS_RE = plan_parser.STATUS_RE
status_state = plan_parser.status_state
parse_plan = plan_parser.parse_plan
plan_date = plan_parser.plan_date
stale_age_days = plan_parser.stale_age_days
STALE_DAYS = plan_parser.STALE_DAYS

TODAY = datetime.date.today().isoformat()


def git_stage_evidence(repo_path):
    """Mine the repo git log for (date, stage_number) references. Used to mark a
    plan's stage as executed when a commit dated >= the plan's date references
    that stage number (best-effort attribution; commit msgs don't name the plan)."""
    repo = Path(repo_path)
    if subprocess.run(["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
                      capture_output=True, text=True).returncode != 0:
        return []
    out = subprocess.run(["git", "-C", str(repo), "log", "--format=%ad|%s", "--date=short"],
                         capture_output=True, text=True).stdout
    pairs = []
    for ln in out.splitlines():
        if "|" not in ln:
            continue
        date, msg = ln.split("|", 1)
        for m in re.finditer(r"[Ss]tage\s+(\d+)", msg):
            pairs.append((date, int(m.group(1))))
    return pairs


def vault_dir():
    """The configured, reachable vault — portfolio-rebuild's one definition of it."""
    return pr.vault_dir()


def existing_sources(backlog_text):
    return set(re.findall(r"^\s*-\s*\*\*Source:\*\*\s*(.+?)\s*$", backlog_text, re.M))


def max_bl(backlog_text):
    ids = [int(m) for m in re.findall(r"^##\s+BL-(\d+)\b", backlog_text, re.M)]
    return max(ids) if ids else 0


def render_entry(bid, c):
    # The originating plan's filename stamp rides along as a tag, so a unified
    # entry stays greppable back to the plan that produced it. The "0000-00-00"
    # sentinel (unstamped filename) is deliberately NOT emitted — a fake date in
    # a tag is worse than no tag.
    stamp = c.get("plan_date")
    tags = "auto-unified" + (f", {stamp}" if stamp and stamp != "0000-00-00" else "")
    return (f"## BL-{bid:03d} — {c['title'][:80]}\n\n"
            f"- **Opened:** {TODAY}\n"
            f"- **Source:** {c['source']}\n"
            f"- **Reason:** Auto-unified from plan ({c['signal']}).\n"
            f"- **Next step:** TBD — opened by unify on {TODAY}; review and refine.\n"
            f"- **Tags:** {tags}\n\n---\n")


HEADER = ("# Backlog\n\nDeferred items from plan execution, code review, or ad-hoc "
          "capture. Entries are removed when implemented; git history is the audit trail.\n\n---\n")


def unify_project(home, write, repo_path, include_stale=False):
    plans_dir = home / "plans"
    if not plans_dir.is_dir():
        return (0, 0, 0)
    gpairs = git_stage_evidence(repo_path)
    cands = []
    for pf in pr.plan_files(plans_dir):
        if pr.not_a_plan(pf):
            continue
        rel = "plans/" + pf.relative_to(plans_dir).as_posix()
        pdate = plan_date(pf.name)
        done_stages = {sn for (cdate, sn) in gpairs if cdate >= pdate}
        text = pf.read_text(errors="ignore")
        normal = parse_plan(text, rel, done_stages)
        for c in normal:
            c["plan_date"] = pdate
        cands.extend(normal)
        if not include_stale:
            continue
        age = stale_age_days(pf.name)
        if age is None or age <= STALE_DAYS:
            continue
        # Signal 3 lowers the bar for an old plan: re-parse with the git-stage
        # suppression lifted, and keep only what signals 1-2 did NOT already
        # emit. It adds items from plans the normal heuristics skip; it never
        # relabels ones they found.
        # Keyed on (source, title), not source alone: the legacy `unchecked-open`
        # locator encodes the Stage but not the Task N.N, so two tasks in one
        # stage whose bullets share a 50-char prefix produce the same source.
        # Deduping on that key would silently DROP a real stale candidate, and a
        # false negative is the worse failure for a register meant to surface
        # forgotten work.
        seen = {(c["source"], c["title"]) for c in normal}
        for c in parse_plan(text, rel, set()):
            if (c["source"], c["title"]) not in seen:
                cands.append(dict(c, signal="stale-plan-unchecked", plan_date=pdate))
    backlog = home / "backlog.md"
    btext = backlog.read_text() if backlog.exists() else HEADER
    have = existing_sources(btext)
    new = [c for c in cands if c["source"] not in have]
    dups = len(cands) - len(new)
    # Deliberately NOT routed through portfolio-rebuild.py's write_if_changed.
    # This is an APPEND to a hand-curated register, not a regenerate-in-place: `btext` is the file's existing bytes carried through
    # untouched and `add` holds only candidates whose Source is absent from them.
    # A changed-check around `btext + add` would compare a strictly longer string
    # and therefore fire every time — a guard that guards nothing. The real guard
    # is `new` above: when every candidate is already registered it is empty and
    # the file is never opened. That holds across a date change even though
    # render_entry() stamps TODAY, because dedup keys on **Source:**, not on the
    # rendered entry. Both halves are pinned by the write-idempotency test,
    # which is what makes this an exception rather than an assertion.
    if write and new:
        nid = max_bl(btext)
        # ensure file ends clean
        if not btext.endswith("\n"):
            btext += "\n"
        add = ""
        for c in new:
            nid += 1
            add += render_entry(nid, c)
        backlog.write_text(btext + add)
    return (len(new), dups, len(cands))


def main():
    ap = argparse.ArgumentParser(
        description="Append backlog candidates from each project's vault plans to its "
                    "vault backlog. Dry run unless --write.")
    ap.add_argument("--write", action="store_true",
                    help="append the new entries (refused while another owner holds the "
                         "vault's maintenance window)")
    ap.add_argument("--project", help="only the registered project at this repo path")
    ap.add_argument("--include-stale", action="store_true",
                    help="also surface unresolved items in plans older than "
                         f"{STALE_DAYS} days by filename stamp (off by default)")
    args = ap.parse_args()
    vd = vault_dir()
    # An entry that keeps its records in its repo has no vault plans or backlog.
    if args.project:
        projects = pr.select_project(pr.load_projects(enabled_only=False), args.project,
                                     enabled_only=True, vault_only=True)
    else:
        projects = [p for p in pr.load_projects() if not pr.records_in_repo(p)]
    if args.write:
        pr.require_write(vd)
    tot_new = tot_dup = tot_cand = 0
    for proj in projects:
        home = vd / "Portfolio" / proj["area"] / proj["name"]
        n, d, c = unify_project(home, args.write, proj["path"], args.include_stale)
        tot_new += n; tot_dup += d; tot_cand += c
        if c:
            print(f"  {proj['area']}/{proj['name']}: {n} new, {d} dup, {c} candidates")
    print(f"\n{'WRITE' if args.write else 'DRY-RUN'}: {tot_new} new entries, "
          f"{tot_dup} duplicates skipped, {tot_cand} candidates across "
          f"{len(projects)} projects")


if __name__ == "__main__":
    main()
