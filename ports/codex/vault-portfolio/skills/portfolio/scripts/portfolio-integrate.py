#!/usr/bin/env python3
"""portfolio-integrate — the cross-project integration graph and its backlog roll-up.

Reads every <vault>/Portfolio/<area>/<name>/integration.md, builds
Portfolio/integration-graph.md (adjacency + symmetry check), and rolls up
every `integration`-tagged backlog entry into Portfolio/integration-backlog.md.

Symmetry rule: if A declares `impacts: [[B]]`, B must declare `depends_on: [[A]]`
(and vice-versa). Asymmetries are reported under `## Asymmetries (review)` and
NEVER auto-fixed. Dangling targets (not a registered project) are flagged.
An entry that sets `records: repo` has no vault home: its backlog under its vault folder
is not its state and is not rolled up. Its integration.md there is read all the same,
because its edges name the owner's other projects and stay in the vault.
--write is refused while another owner holds the vault's maintenance window.

See references/integration-format.md for the per-project file schema.
"""
import argparse, importlib.util, re, sys, datetime
from pathlib import Path

# `write_if_changed` is portfolio-rebuild.py's, and it is imported rather than
# copied because it carries a CONTRACT, not just three lines: regenerate the
# document, strip the `**Last rebuilt:**` line, and write only if the rest
# differs. Both roll-ups here embed that timestamp, so without it every run
# would rewrite both files — on a synced vault with no version control, where a
# needless write means sync churn and conflict copies, and where an unchanged
# mtime is the operator's only "nothing moved" signal. A second copy of the
# function would be a second place for that contract to drift.
_REBUILD = Path(__file__).resolve().parent / "portfolio-rebuild.py"
_spec = importlib.util.spec_from_file_location("portfolio_rebuild", _REBUILD)
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)
write_if_changed = pr.write_if_changed

TODAY = datetime.date.today().isoformat()


def vault_dir():
    """The configured, reachable vault — portfolio-rebuild's one definition of it."""
    return pr.vault_dir()


def outside(path, skip):
    """True unless `path` lies under one of the `skip` folders."""
    return not any(h in path.parents for h in skip)


def build_graph(vd, registered_names, skip=()):
    depends, impacts = {}, {}   # name -> [(target, why)]
    # portfolio-rebuild's one reader of the format; a file it cannot read refuses
    # the run before anything is rendered or written. `skip` holds vault folders
    # whose integration.md is not read. main() passes none: an entry that keeps its
    # records in its repo still keeps its edges in the vault, because they name the
    # owner's other projects.
    parsed = pr.read_integrations(sorted(f for f in (vd / "Portfolio").rglob("integration.md")
                                         if outside(f, skip)),
                                  "portfolio-integrate")
    for f, fm in parsed.items():
        name = fm.get("project") or f.parent.name
        depends[name] = pr.frontmatter_edges(fm, "depends_on")
        impacts[name] = pr.frontmatter_edges(fm, "impacts")

    # symmetry + dangling checks
    asymmetries, dangling = [], []
    for a, deps in depends.items():
        for (b, why) in deps:
            if b not in registered_names:
                dangling.append(f"{a} depends_on [[{b}]] — unresolved target (not a registered project)")
            elif a not in [t for (t, _) in impacts.get(b, [])]:
                asymmetries.append(f"{a} depends_on [[{b}]], but [[{b}]] does not list `impacts: [[{a}]]`")
    for a, imps in impacts.items():
        for (b, why) in imps:
            if b not in registered_names:
                dangling.append(f"{a} impacts [[{b}]] — unresolved target (not a registered project)")
            elif a not in [t for (t, _) in depends.get(b, [])]:
                asymmetries.append(f"{a} impacts [[{b}]], but [[{b}]] does not list `depends_on: [[{a}]]`")
    return depends, impacts, sorted(set(asymmetries)), sorted(set(dangling))


def render_graph(depends, impacts, asymmetries, dangling):
    L = ["# Integration Graph", "",
         "Auto-generated from every `Portfolio/<area>/<project>/integration.md` by",
         "`$vault-portfolio:portfolio integrate`. Edges are declared per-project and",
         "symmetry-checked here. Do not hand-edit — edit the per-project files.", "",
         f"**Last rebuilt:** {TODAY}", "", "---", "", "## Edges (depends_on → upstream)", ""]
    for a in sorted(depends):
        for (b, why) in depends[a]:
            L.append(f"- `{a}` → `{b}`  — {why}")
    L += ["", "## Asymmetries (review)", ""]
    if asymmetries:
        L += [f"- ⚠ {x}" for x in asymmetries]
    else:
        L.append("_None — every declared edge is reciprocated._")
    if dangling:
        L += ["", "## Unresolved targets", ""] + [f"- ❓ {x}" for x in dangling]
    L.append("")
    return "\n".join(L)


def rollup_integration_backlog(vd, skip=()):
    """Scan every project backlog for integration-tagged entries; group by edge.
    Backlogs under a `skip` folder (see build_graph) are not read."""
    rows = []  # (edge, project, bl_id, title)
    for bl in sorted(f for f in (vd / "Portfolio").rglob("backlog.md") if outside(f, skip)):
        proj = bl.parent.name
        text = bl.read_text(errors="ignore")
        for block in re.findall(r"^## (BL-\d+) — (.+?)\n(.*?)(?=^## BL-|\Z)", text, re.S | re.M):
            bid, title, body = block
            if re.search(r"^\s*-?\s*\*?\*?Tags:\*?\*?.*\bintegration\b", body, re.M) or \
               re.search(r"^\s*-?\s*\*?\*?Integration:\*?\*?", body, re.M):
                em = re.search(r"edge=([^\s]+)|plan=([^\s]+)", body)
                edge = (em.group(1) or em.group(2)) if em else "unspecified"
                rows.append((edge, proj, bid, title.strip()))
    L = ["# Integration Backlog", "",
         "Every `integration`-tagged backlog item across all projects, grouped by",
         "edge. Auto-generated by `$vault-portfolio:portfolio integrate`. The items live in",
         "their project's own backlog; this is a cross-project rollup view.", "",
         f"**Last rebuilt:** {TODAY}", "", "---", ""]
    if not rows:
        L += ["_No integration-tagged backlog items yet._", ""]
    else:
        by_edge = {}
        for edge, proj, bid, title in rows:
            by_edge.setdefault(edge, []).append((proj, bid, title))
        for edge in sorted(by_edge):
            L.append(f"## edge: {edge}")
            L.append("")
            for proj, bid, title in by_edge[edge]:
                L.append(f"- `{proj}` {bid} — {title}")
            L.append("")
    return "\n".join(L), len(rows)


def main():
    ap = argparse.ArgumentParser(
        description="Build Portfolio/integration-graph.md and integration-backlog.md "
                    "from every project's integration.md. Dry run unless --write.")
    ap.add_argument("--write", action="store_true",
                    help="write both roll-ups (refused while another owner holds the "
                         "vault's maintenance window)")
    args = ap.parse_args()
    vd = vault_dir()
    everything = pr.load_projects(enabled_only=False)
    names = {p["name"] for p in everything}
    # An entry that keeps its records in its repo has no vault home: its backlog
    # there is not its state, so the integration backlog skips that folder. Its
    # integration.md is read all the same: the edges name the
    # owner's other projects, so they stay in the vault rather than in a public repo.
    skip = {vd / "Portfolio" / p["area"] / p["name"] for p in everything
            if pr.records_in_repo(p)}
    if args.write:
        pr.require_write(vd)

    depends, impacts, asym, dangling = build_graph(vd, names)
    graph_md = render_graph(depends, impacts, asym, dangling)
    ibl_md, n_items = rollup_integration_backlog(vd, skip)

    n_edges = sum(len(v) for v in depends.values())
    print(f"edges: {n_edges} | asymmetries: {len(asym)} | dangling: {len(dangling)} | integration-backlog items: {n_items}")
    for x in asym:
        print(f"  ⚠ {x}")
    if args.write:
        # Reported per file, and "unchanged" is reported as loudly as "wrote":
        # a run that says it wrote nothing is the evidence that the no-change
        # path is live.
        wrote, same = [], []
        for fn, body in (("integration-graph.md", graph_md),
                         ("integration-backlog.md", ibl_md)):
            (wrote if write_if_changed(vd / "Portfolio" / fn, body) else same).append(fn)
        print(f"wrote: {', '.join(wrote) or 'nothing'} | "
              f"unchanged: {', '.join(same) or 'nothing'}")
    else:
        print("(dry-run — pass --write to persist)")


if __name__ == "__main__":
    main()
