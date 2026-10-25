#!/usr/bin/env python3
"""compass-scan — deterministic evidence lane for the compass skill.

Walks the registry (`_config.registry_path()`) and, per enabled project, gathers the
work-state evidence the compass SKILL.md ranks: in-flight plan state (read through
the vendored plan parser — one contract, one implementation), backlog open/parked
counts, maturity axis summary, decision-register summary, integration-graph edges,
git recency and, when a business scanner is configured, its per-project state.
Emits ONE JSON document on stdout.

Where things come from:
  vault      `_config.vault_setting()`, checked by portfolio-rebuild.py's
             vault_problem(), the one definition of a reachable vault
  registry   `_config.registry_path()`
  business   `_config.business_scan()`: an argv, or None when the layer is off

Read-only by construction: never writes under the vault or any repo.
Projects that cannot be assessed land in `couldnt_assess` with a reason —
never silently dropped. An entry that sets `records: repo` is one: it has no
vault home, so its reason says so and nothing under its old vault path is read. No LLM in this lane; judgment lives in SKILL.md.

Exit codes: 0 the JSON document · 1 unconfigured or unreachable vault, or a registry
that is missing or malformed (nothing on stdout) · 2 a config file that does not parse.
"""
import argparse
import datetime
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

# _config.py is the one import hub: it finds the plugin root and loads the vendored
# parser and sibling scripts by path. It sits in the portfolio skill's scripts/.
_cspec = importlib.util.spec_from_file_location(
    "_vault_portfolio_config",
    Path(__file__).resolve().parents[2] / "portfolio" / "scripts" / "_config.py")
_config = importlib.util.module_from_spec(_cspec)
sys.modules[_cspec.name] = _config
_cspec.loader.exec_module(_config)

# The plan-status contract (what `[ ]` / `[x]` / `[~]` mean, and why abandonment is
# a structured **Abandoned:** marker rather than a prose-banner heuristic) is defined
# and argued once, in the vendored parser at STATUS_RE. Read it there before changing
# anything here. This module classifies via pp.status_state() and never tests the
# captured character directly.
pp = _config.load_module("vendor/staged_planning/plan_parser.py")

_PR = None


def rebuild():
    """portfolio-rebuild.py as a module, loaded on first use.

    It owns the decisions.md contract (block boundaries, required fields, the
    degrade-never-drop rule for a malformed heading) and vault_problem(), the one
    definition of a reachable vault. Reimplementing either here would fork it.
    """
    global _PR
    if _PR is None:
        _PR = _config.load_module("skills/portfolio/scripts/portfolio-rebuild.py")
    return _PR


def not_configured(msg):
    print(f"portfolio not configured: {msg}", file=sys.stderr)
    sys.exit(1)


def load_env():
    try:
        vault, source = _config.vault_setting()
        registry = _config.registry_path()
    except _config.ConfigError as e:
        print(f"compass-scan: {e}", file=sys.stderr)
        sys.exit(2)
    if vault is None:
        not_configured("no vault is set (OBSIDIAN_VAULT_PATH, `default_vault` in "
                       "~/.config/obsidian-wiki/config.json, or `vault_dir` in "
                       "~/.claude/portfolio-config.yaml)")
    # The one registry validator, not a local reading of it: a missing file, bad
    # YAML, no `projects:` list or a malformed entry is refused (exit 1, nothing on
    # stdout), never dropped from the list, so the summary cannot under-count.
    projects = rebuild().load_projects(path=registry, exit_code=1)
    # A set-but-unreachable vault is REFUSED. This script emits ONE JSON document,
    # and against an unreachable vault every project would simply fail to resolve
    # a portfolio home: the envelope would still be well-formed, `projects` would
    # be empty, and the skill reading it — whose own rule is "never present a fact
    # the JSON doesn't back" — would truthfully report that nothing is in flight
    # across the whole portfolio. That is the empty-results-as-truth failure, and
    # no per-project `couldnt_assess` reason fixes it, because the answer the
    # operator acts on is the summary. A non-zero exit with nothing on stdout
    # cannot be mistaken for an answer.
    # Delegated, not restated, and called unconditionally: a guard in front of the
    # delegate that copies one of its branches would stop growing the day the
    # delegate grows another.
    path, problem = rebuild().vault_problem(vault, source)
    if problem:
        print(problem, file=sys.stderr)
        sys.exit(1)
    return path, projects


def _add_note(state, msg):
    """Accumulate a plan note. Notes are diagnostics the operator must see —
    an abandon advisory and a stale-close-out warning can both be true of one
    plan, so they concatenate rather than the later one silently winning."""
    state["note"] = f"{state['note']}; {msg}" if state.get("note") else msg


def plan_state(text, fname, path=None):
    """State of one plan file, via the vendored parser's Status contract.
    Returns None for master plans (register format — no Task context, tracked
    through their sub-plans instead)."""
    # Master detection is explicit (filename OR heading): without this filter a
    # master would fall into the "legacy/malformed" degrade branch below and emit
    # a spurious unmeasurable entry.
    if pp.is_master_plan(text, fname):
        return None
    cm = pp.COMPLETED_RE.search(text)
    completed = cm.group(1).split()[0] if cm and cm.group(1).split() else None
    abandoned, abandon_advisory, abandon_reason = pp.plan_terminal_state(text)
    tasks = []          # (stage, num, desc, state) — state per pp.status_state
    cur_stage = None
    cur_task = None
    for line in text.splitlines():
        sh = pp.STAGEHDR_RE.match(line)
        if sh:
            cur_stage = int(sh.group(1))
        tm = pp.TASK_RE.match(line)
        if tm:
            cur_task = (cur_stage, tm.group(1), tm.group(2).strip())
        sm = pp.STATUS_RE.match(line)
        if sm and cur_task:
            # Classify via the contract's helper, never `!= " "`: that idiom
            # reads a `[~]` partial task as DONE.
            tasks.append(cur_task + (pp.status_state(sm.group(1)),))
            cur_task = None
    # A partial task is unfinished work: it counts toward `total` (the plan is
    # less finished, not smaller) but never toward `done`.
    state = {"file": fname, "active": True, "stage": None, "next_task": None,
             "done": sum(1 for t in tasks if t[3] == "done"),
             "partial": sum(1 for t in tasks if t[3] == "partial"),
             "total": len(tasks), "abandoned": abandoned,
             # SKILL.md lists a suppressed plan WITH its reason — the scanner
             # must therefore carry it, not just the boolean.
             "abandoned_reason": abandon_reason,
             "completed": completed, "note": None,
             # Zero parseable Status fields — no stage, no next task, no
             # done/total. Carried as its own flag rather than left for a
             # consumer to infer from `total == 0`: a plan can reach zero tasks
             # by being unparseable, and that is the one case where every other
             # field in this dict is empty for a reason the reader must know.
             # Set in the `if not tasks:` branch below, where the bucket is argued.
             "unmeasurable": False,
             # A `[~]` gate check says a check could not be RUN — the one thing
             # no task marker can express. Carried here because compass retires a
             # plan whose tasks are all done, and a blocked plan that retires is a
             # plan nobody looks at again. Through plan_blocked(), so
             # `**Blocked-accepted:**` retires it again and a master inherits its
             # sub-plans' state.
             "blocked_gate": pp.plan_blocked(text, path)[0]}
    if abandoned:
        # Terminal state: parsed and listed like any other plan, but never
        # ranked as available work (see rank-eligible filtering in SKILL.md).
        state["active"] = False
    if abandon_advisory:
        _add_note(state, abandon_advisory)
    if not tasks:
        # legacy/malformed plan: degrade, never drop — and never count it as
        # in-flight. Nothing in it says what stage it is at, what comes next, or
        # how much is left, so counting it among in-flight work would pad that
        # population with an item no reader can act on and no gate can check.
        # It gets its own bucket instead. plan-status-audit.py reaches the same
        # split by its own route: a plan with no Status fields is `no-status`
        # there, never `started-unfinished`.
        # Suppressed from the in-flight count, NOT hidden: the entry is still
        # emitted with its note, and compass SKILL.md lists the bucket in
        # `review` so a legacy plan never becomes invisible by being quiet.
        state["unmeasurable"] = True
        state["active"] = False
        # "no Status fields the PARSER found", not "no Status fields": a plan can
        # carry perfectly good `- **Status:** [ ]` lines and still land here when
        # its task headings are `#### Task` rather than `### Task`, because TASK_RE
        # never matches and no Status line is ever attributed. Sending the author
        # to the Status fields would point at the one part of the file that is fine.
        _add_note(state, "stage unknown (no task/Status pair the parser could read "
                         "— check the `### Task N.M` heading level too) — "
                         "legacy/unmeasurable, not counted as in-flight")
        return state
    # Partial tasks are still open: an in-flight task is the natural `next_task`
    # and must not let a plan read as finished.
    open_tasks = [t for t in tasks if t[3] != "done"]
    if open_tasks:
        stage, num, desc, _ = open_tasks[0]
        state["stage"] = stage
        state["next_task"] = f"Task {num}: {desc}"
        if cm:
            # Append, never overwrite: a banner advisory may already be here,
            # and SKILL.md's hard rule is that the advisory is always surfaced.
            _add_note(state,
                      f"completed marker present but {len(open_tasks)} task(s) still open")
    else:
        # All tasks done — but "done" is about tasks, and a gate check that could
        # not run is about proof. Retiring on the weaker fact would hide exactly
        # the plan that still needs a look, so a blocked gate keeps the plan on
        # the board with its reason attached.
        if state["blocked_gate"]:
            _add_note(state, "all tasks done but a stage-gate check is `[~]` BLOCKED")
        else:
            state["active"] = False
            if not cm and not abandoned:
                _add_note(state, "all tasks done but no close-out line")
    return state


def collect_plans(home):
    """One state per plan in the home's plans/, nested sets included.

    The files come from portfolio-rebuild's plan_files(), the enumeration
    plan-status-audit and unify read too, so all three see one corpus; which of
    them is a plan is portfolio-rebuild's not_a_plan(), the exclusion unify and
    plan-status-audit share (the parser's is_not_a_plan(), plus a README.md or
    backlog.md kept in plans/). A plan's `file` is
    its path under plans/, so two sets that each hold a `00-overview.md` stay two
    entries.
    """
    plans_dir = home / "plans"
    if not plans_dir.is_dir():
        return []
    out = []
    for pf in rebuild().plan_files(plans_dir):
        if rebuild().not_a_plan(pf):
            continue
        rel = pf.relative_to(plans_dir).as_posix()
        st = plan_state(pf.read_text(errors="ignore"), rel, pf)
        if st is not None:
            out.append(st)
    return out


PARKED_RE = re.compile(r"^\s*-\s*\*\*Parked:\*\*\s*(.+)$", re.I | re.M)
AXIS_RE = re.compile(r"^##\s+(.+)$")
MBOX_RE = re.compile(r"^\s*-\s*\[(x|X| |N/A)\]", re.I)
EDGE_RE = re.compile(r"^-\s*`([^`]+)`\s*→\s*`([^`]+)`\s*—\s*(.*)$")


def collect_git(path):
    r = subprocess.run(["git", "-C", str(path), "log", "-1", "--format=%ct"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None, "git: " + (r.stderr.strip().splitlines() or ["not a git repository"])[0]
    ts = int(r.stdout.strip())
    # %ct is a UTC epoch; convert in UTC so age_days is host-TZ-independent
    utc = datetime.timezone.utc
    last = datetime.datetime.fromtimestamp(ts, tz=utc).date()
    today = datetime.datetime.now(tz=utc).date()
    return {"last_commit": last.isoformat(),
            "age_days": (today - last).days}, None


def collect_backlog(home):
    f = home / "backlog.md"
    if not f.exists():
        return {"open": 0, "parked": 0, "parked_items": []}
    parked_items = []
    open_n = parked_n = 0
    for block in f.read_text(errors="ignore").split("\n## ")[1:]:
        m = re.match(r"BL-\d+\s*—\s*(.+)", block)
        if not m:
            continue
        open_n += 1
        pm = PARKED_RE.search(block)
        if pm:
            parked_n += 1
            parked_items.append({"title": m.group(1).strip(),
                                 "note": pm.group(1).strip()})
    return {"open": open_n, "parked": parked_n, "parked_items": parked_items}


def collect_maturity(home):
    f = home / "MATURITY.md"
    if not f.exists():
        return None
    axes = {}
    cur = None
    for line in f.read_text(errors="ignore").splitlines():
        am = AXIS_RE.match(line)
        if am:
            cur = am.group(1).strip()
            axes[cur] = {"done": 0, "open": 0, "na": 0}
            continue
        bm = MBOX_RE.match(line)
        if bm and cur:
            mark = bm.group(1).lower()
            key = "done" if mark == "x" else ("na" if mark == "n/a" else "open")
            axes[cur][key] += 1
    axes = {k: v for k, v in axes.items() if sum(v.values())}
    return {"axes": axes,
            "done": sum(a["done"] for a in axes.values()),
            "open": sum(a["open"] for a in axes.values())}


def collect_decisions(home):
    """(summary, errors) — summary is None when the project has no decisions.md.

    Malformed entries (`id is None`) are excluded from count/domains/last_decided:
    a heading the parser could not key must not inflate a count or, worse,
    contribute a stray `Decided` date that reads as the project's most recent
    decision. They are surfaced as `malformed` instead of dropped, so a compass
    ranking sees the same "this register needs cleanup" signal that the
    decisions roll-up's Malformed-entries section shows.

    Returns errors rather than raising: read_project_decisions degrades
    internally, so register-level problems arrive as data and the dispatch
    loop's try/except would never see them.
    """
    pr = rebuild()
    blk = pr.read_project_decisions(home)
    if blk is None:
        return None, []
    entries = [e for e in blk["entries"] if e.get("id")]
    dates = [e["fields"].get("Decided") for e in entries if e["fields"].get("Decided")]
    malformed = (sum(1 for e in blk["entries"] if not e.get("id"))
                 + sum(1 for e in entries if e.get("missing") or e.get("duplicates")))
    return {"count": len(entries),
            "malformed": malformed,
            "domains": sorted({d for e in entries for d in pr.decision_domains(e)}),
            "last_decided": max(dates) if dates else None}, list(blk["errors"])


def load_edges(vault):
    """Parse integration-graph.md once: list of (dependent, upstream, why)."""
    f = vault / "Portfolio" / "integration-graph.md"
    if not f.exists():
        return []
    edges = []
    for line in f.read_text(errors="ignore").splitlines():
        em = EDGE_RE.match(line.strip())
        if em:
            edges.append((em.group(1), em.group(2), em.group(3).strip()))
    return edges


def scan_project(proj, vault):
    """Assess one registry project. Returns (entry, None) or (None, reason)."""
    path = Path(proj["path"])
    if not path.exists():
        return None, "path does not exist"
    entry = {
        "name": proj["name"],
        "area": proj["area"],
        "path": str(path),
        "errors": [],
    }
    home = vault / "Portfolio" / proj["area"] / proj["name"]
    # Keyword form: each key is the entry's JSON key, (collector, fallback) its value.
    collectors = dict(
        plans=(lambda: collect_plans(home), []),
        backlog=(lambda: collect_backlog(home),
                 {"open": 0, "parked": 0, "parked_items": []}),
        maturity=(lambda: collect_maturity(home), None),
        decisions=(lambda: collect_decisions(home), None),
    )
    for key, (fn, fallback) in collectors.items():
        try:
            res = fn()
        except Exception as e:  # degrade per collector, never drop the project
            entry[key] = fallback
            entry["errors"].append(f"{key}: {e}")
            continue
        # A collector may return (value, errors) to report problems it handled
        # internally rather than raised — the only way a source that degrades on
        # its own (read_project_decisions) can still surface what it found.
        if isinstance(res, tuple):
            res, errs = res
            entry["errors"] += [f"{key}: {m}" for m in errs]
        entry[key] = res
    try:
        git_info, git_err = collect_git(path)
    except Exception as e:  # git binary/exec failure degrades like any collector
        git_info, git_err = None, f"git: {e}"
    entry["git"] = git_info
    if git_err:
        entry["errors"].append(git_err)
    return entry, None


def business_map():
    """Optional business state keyed by project name — {} when no business scanner
    is configured (additive: compass works identically without it).

    The scanner is `_config.business_scan()`: $BUSINESS_SCAN_PATH, else the
    `business_scan` argv in the obsidian-wiki config. No other plugin is probed
    for; a business layer is whatever the owner configured, or nothing.

    A business group (`group: true`) is NOT a registry project and gets no key of
    its own: its state is fanned out to each member under the qualified
    "<area>/<name>" key it declares, tagged with `group: <slug>`, so a per-project
    view still answers "does this repo have a business case". A scanner that emits
    no group keys takes the plain per-project path unchanged.

    NEVER raises: the business layer is optional and independently versioned, so
    ANY failure (bad config, nonzero exit, timeout, malformed/unexpected-shape
    JSON) degrades to {} — a broken business scanner must not take down compass's
    plan/backlog/maturity evidence."""
    try:
        argv = _config.business_scan()
    except _config.ConfigError:
        return {}
    if not argv:
        return {}
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return {}
        doc = json.loads(r.stdout)
        if not isinstance(doc, dict):
            return {}
        out = {}
        for p in doc.get("projects", []):
            if not isinstance(p, dict) or not p.get("name") or not p.get("assessed"):
                continue
            gtm = p.get("gtm") if isinstance(p.get("gtm"), dict) else None
            model = (p.get("monetization") or {}).get("model") \
                if isinstance(p.get("monetization"), dict) else None
            research = p.get("research") if isinstance(p.get("research"), dict) else None
            plan = p.get("plan") if isinstance(p.get("plan"), dict) else None
            block = {
                "verdict": p.get("verdict"),
                "model": model,
                "gtm_pct": gtm.get("pct") if gtm else None,
                "last_reviewed_age_days": p.get("last_reviewed_age_days"),
                # research/plan age (days) when the artifact exists, else None — so compass
                # can flag stale market-research/plan alongside stale review. Additive.
                "research_age_days": research.get("age_days")
                    if research and research.get("exists") else None,
                "plan_age_days": plan.get("age_days")
                    if plan and plan.get("exists") else None,
                "stage": ("tracked" if p.get("metrics") else "launched" if gtm
                          else "modeled" if model else "assessed"),
            }
            if p.get("group"):
                members = p.get("members")
                if not isinstance(members, list):
                    continue
                for m in members:
                    # Qualified key only: a group's state must never land on a
                    # same-named project in another area.
                    if isinstance(m, str) and "/" in m:
                        out[m] = dict(block, group=p["name"])
            else:
                out[p["name"]] = block
        return out
    except Exception:      # timeout, JSON error, unexpected shape — degrade to no layer
        return {}


# The plans each mode reads (SKILL.md § now / next / review). A plan that is none of
# active, abandoned, unmeasurable or noted is simply done, and no mode lists it.
VIEWS = {"now": {"active", "noted"}, "next": {"active"},
         "review": {"active", "noted", "abandoned", "unmeasurable"}}


def plan_kind(plan):
    if plan.get("active"):
        return "active"
    for k in ("abandoned", "unmeasurable"):
        if plan.get(k):
            return k
    return "noted" if plan.get("note") else "done"


def view(doc, mode):
    """The document cut to what `mode` reads: each project keeps the plans of the kinds
    VIEWS names and counts the rest in plans_omitted; `now` also drops a project with
    no such plan and no error."""
    keep, projects = VIEWS[mode], []
    for pr in doc["projects"]:
        kept = [p for p in pr["plans"] if plan_kind(p) in keep]
        omitted = {}
        for p in pr["plans"]:
            if plan_kind(p) not in keep:
                omitted[plan_kind(p)] = omitted.get(plan_kind(p), 0) + 1
        if mode == "now" and not kept and not pr["errors"]:
            continue
        projects.append({**pr, "plans": kept, "plans_omitted": omitted})
    return {**doc, "mode": mode, "projects": projects}


def prune(o):
    """Drop null, false and empty values, at every depth (--compact)."""
    if isinstance(o, dict):
        kept = {k: prune(v) for k, v in o.items()}
        return {k: v for k, v in kept.items() if v not in (None, False, [], {}, "")}
    if isinstance(o, list):
        return [prune(v) for v in o]
    return o


def page(doc, part, budget, size):
    """Part `part` (1-based) of the document: the projects packed in order into parts of
    at most `budget` bytes each by `size` (a project larger than the budget gets a part
    to itself). couldnt_assess rides in part 1 only. None when `part` is past the last."""
    parts, cur, used = [], [], 0
    for pr in doc["projects"]:
        n = size(pr)
        if cur and used + n > budget:
            parts.append(cur)
            cur, used = [], 0
        cur.append(pr)
        used += n
    parts.append(cur)
    if not 1 <= part <= len(parts):
        return None
    out = {k: v for k, v in doc.items() if k not in ("projects", "couldnt_assess")}
    out.update(part=part, parts=len(parts), projects=parts[part - 1])
    if part == 1:
        out["couldnt_assess"] = doc["couldnt_assess"]
    return out


def main():
    # --help answers before any configuration is read: a help request that fails on
    # an unconfigured machine tells the caller nothing about what the script does.
    ap = argparse.ArgumentParser(
        prog="compass-scan.py",
        description="Gather every enabled registry project's work-state evidence from "
                    "the vault into one JSON document on stdout. Read-only.",
        epilog="Exit codes: 0 the JSON document; 1 unconfigured or unreachable vault, or "
               "a registry that is missing or malformed; 2 a config file that does not "
               "parse, a bad argument, or a --part past the last.")
    ap.add_argument("--mode", choices=sorted(VIEWS),
                    help="keep only the plans that mode reads; count the rest per project")
    ap.add_argument("--compact", action="store_true",
                    help="one line, without null, false or empty fields")
    ap.add_argument("--part", type=int, metavar="N",
                    help="print part N of the projects; each part names how many there are")
    ap.add_argument("--part-bytes", type=int, default=24000, metavar="B",
                    help="the byte budget of one part (default 24000)")
    args = ap.parse_args()
    vault, projects = load_env()
    out = {
        "generated": datetime.date.today().isoformat(),
        "vault_dir": str(vault),
        "projects": [],
        "couldnt_assess": [],
    }
    edges = load_edges(vault)
    biz = business_map()            # {} when no scanner is configured → no per-project key
    for proj in projects:
        # An entry that keeps its records in its repo has no vault home to read;
        # it is listed with the reason, never assessed from a stale vault folder.
        if rebuild().records_in_repo(proj):
            out["couldnt_assess"].append(
                {"name": proj.get("name"), "area": proj.get("area"),
                 "path": proj.get("path"), "reason": rebuild().OPTED_OUT})
            continue
        try:
            entry, reason = scan_project(proj, vault)
            if entry is not None:
                name = entry["name"]
                entry["dependents"] = [
                    {"project": a, "why": w} for a, b, w in edges if b == name]
                entry["depends_on"] = [
                    {"project": b, "why": w} for a, b, w in edges if a == name]
                # Grouped members are keyed "<area>/<name>"; ungrouped projects
                # keep the bare-name key, so the fallback preserves that path.
                bz = biz.get(f"{entry['area']}/{name}") or biz.get(name)
                if bz is not None:
                    entry["business"] = bz
        except Exception as e:  # a broken project must not abort the sweep
            entry, reason = None, f"scan error: {e}"
        if entry is None:
            out["couldnt_assess"].append(
                {"name": proj.get("name"), "area": proj.get("area"),
                 "path": proj.get("path"), "reason": reason})
        else:
            out["projects"].append(entry)
    if args.mode:
        out = view(out, args.mode)

    def dumps(o):
        if args.compact:
            return json.dumps(prune(o), separators=(",", ":"), ensure_ascii=False)
        return json.dumps(o, indent=1)

    if args.part is not None:
        out = page(out, args.part, args.part_bytes, lambda pr: len(dumps(pr)))
        if out is None:
            print(f"compass-scan: --part {args.part} is past the last part", file=sys.stderr)
            sys.exit(2)
    print(dumps(out))


if __name__ == "__main__":
    main()
