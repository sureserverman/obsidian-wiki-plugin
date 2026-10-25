#!/usr/bin/env python3
"""The decisions register lane of portfolio-rebuild (per-project + per-domain).

Asserts the behaviours that make the register trustworthy:

  * a block missing a required field is FLAGGED, never dropped — an invisible
    decision is worse than a malformed one, since the register's whole job is
    that nothing binding goes unrecorded;
  * block boundaries are any `## ` heading, so a mistyped heading is flagged in
    place rather than vanishing or being swallowed into its neighbour;
  * link symmetry is checked in BOTH directions (project Global: ↔ domain
    Applies to:) and reported, never auto-repaired — auto-fixing would assert
    an edge about a project the run has not read;
  * a link whose target does not exist is `unresolved`, distinct from an
    asymmetry, because the two need different fixes;
  * wrapped prose and nested list bullets both parse as one field value;
  * a project with no decisions.md contributes nothing and errors nothing;
  * the roll-up, the sidecar pointer and the read-only guarantee.

The fixture tree (fixtures/decisions) writes its ids as placeholders; expand_ids()
spells them out in a temp copy. Stdlib only, no pytest. Run:
  python3 -I src/vault-portfolio/core/skills/portfolio/tests/test-portfolio-decisions.py
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures/decisions"

for _k in list(os.environ):
    if _k.startswith(("OBSIDIAN_", "BUSINESS_", "VAULT_CONTEXT_")):
        os.environ.pop(_k)
_HOME = tempfile.mkdtemp(prefix="decisions-home-")
os.environ["HOME"] = _HOME

_spec = importlib.util.spec_from_file_location(
    "portfolio_rebuild", HERE.parent / "scripts" / "portfolio-rebuild.py")
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)

# Spelled apart so this file carries no literal register id.
DEC, GDEC = "DEC", "GDEC"
MOB = f"{GDEC}-MOB"

fails: list[str] = []


def chk(cond, msg):
    if not cond:
        fails.append(msg)


def entry(entries, eid):
    for e in entries:
        if e["id"] == eid:
            return e
    return None


def expand_ids(root: Path):
    for p in root.rglob("*.md"):
        t = p.read_text(encoding="utf-8")
        p.write_text(t.replace("{DEC}", "DEC").replace("{GDEC}", "GDEC").replace("{BL}", "BL"),
                     encoding="utf-8")


def run(vault: Path) -> None:
    port = vault / "Portfolio"

    # ---- per-project parse ------------------------------------------------
    app = pr.read_project_decisions(port / "apps" / "example-app")
    chk(app is not None, "example-app decisions.md should be found")
    ids = [e["id"] for e in app["entries"]]
    chk(ids == [f"{DEC}-007", f"{DEC}-006", f"{DEC}-005"], f"newest-first block order broken: {ids}")

    d7 = entry(app["entries"], f"{DEC}-007")
    chk(d7["title"] == "Sync runs in a background worker, not on the UI thread",
        f"title parse: {d7['title']!r}")
    chk(d7["missing"] == [], f"{DEC}-007 is complete, got missing={d7['missing']}")
    chk("stalls input whenever the network is" in d7["fields"]["Reason"],
        "wrapped Reason prose must join across lines")
    chk("a queue between the two" in d7["fields"]["Reason"],
        "wrapped Reason must include its final line")
    chk("---" not in d7["fields"]["Reason"],
        "block separator must not bleed into the last field")
    chk(pr.decision_domains(d7) == ["mobile", "network"], f"domains: {pr.decision_domains(d7)}")

    d6 = entry(app["entries"], f"{DEC}-006")
    chk(d6["fields"]["Status"] == f"superseded by {DEC}-007", "superseded status must survive")

    # degrade-never-drop: the third block lacks Domains / Source / Reason
    d5 = entry(app["entries"], f"{DEC}-005")
    chk(d5 is not None, "malformed block must still be returned, not dropped")
    chk(sorted(d5["missing"]) == ["Domains", "Reason", "Source"],
        f"malformed block must be flagged: {d5['missing']}")

    # `Domains: none` yields no domains but is not malformed
    orphan = pr.read_project_decisions(port / "tools" / "orphan-proj")
    o1 = entry(orphan["entries"], f"{DEC}-001")
    chk(o1["missing"] == [], f"'none' is a valid Domains value: {o1['missing']}")
    chk(pr.decision_domains(o1) == [], "'none' must expand to zero domains")

    chk(pr.read_project_decisions(port / "apps" / "does-not-exist") is None,
        "a project with no decisions.md must return None, not an error")

    # ---- malformed HEADINGS (not just missing fields) ----------------------
    mh = pr.read_project_decisions(port / "apps" / "malformed-headings")
    hids = [e["id"] for e in mh["entries"]]
    chk(hids == [None, f"{DEC}-002", None, f"{DEC}-001", None],
        f"malformed headings must be flagged in place, not dropped: {hids}")

    bad_first = mh["entries"][0]
    chk(bad_first["malformed_heading"] is True, "first-in-file bad heading must be flagged")
    chk("Hyphen instead of em-dash" in bad_first["heading"],
        f"raw heading must be preserved for the report: {bad_first['heading']!r}")
    chk("vanish without trace" in bad_first["fields"].get("Reason", ""),
        "a malformed-heading block must still have its body parsed")

    good = entry(mh["entries"], f"{DEC}-002")
    chk("swallow this into" not in good["fields"]["Reason"],
        f"following malformed block must NOT bleed into the previous Reason: "
        f"{good['fields']['Reason']!r}")
    chk(good["fields"]["Reason"] == "Final reason line.",
        f"Reason must end at the block boundary: {good['fields']['Reason']!r}")
    chk(good["duplicates"] == ["Status"],
        f"a repeated field must be flagged, not silently overwritten: {good['duplicates']}")
    chk("***" not in good["fields"]["Reason"],
        "non-hyphen horizontal rules must not leak into a field value")

    last = entry(mh["entries"], f"{DEC}-001")
    chk(last["fields"]["Reason"] == "Intact.", "the final well-formed block must survive intact")

    # ---- optional project tag ---------------------------------------------
    # A 2-4 letter uppercase tag keys the entry like the untagged form, so an id
    # cited from another project's plan can say whose decision it is.
    tagged = pr.parse_decision_file(
        f"## {DEC}-AB-003 — Tagged\n\n- **Decided:** 2026-01-02\n- **Status:** accepted\n"
        "- **Domains:** network\n- **Source:** direct\n- **Reason:** Because.\n\n"
        f"## {DEC}-004 — Untagged\n\n- **Decided:** 2026-01-03\n- **Status:** accepted\n"
        "- **Domains:** none\n- **Source:** direct\n- **Reason:** Also because.\n\n"
        f"## {DEC}-ab-005 — Lowercase tag\n\n- **Reason:** Not a tag.\n\n"
        f"## {DEC}-TOOLONG-006 — Overlong tag\n\n- **Reason:** Not a tag either.\n",
        pr.DEC_ID_RE, pr.PROJECT_REQUIRED)
    tids = [e["id"] for e in tagged]
    chk(tids == [f"{DEC}-AB-003", f"{DEC}-004", None, None],
        f"a 2-4 letter uppercase tag must key the entry; anything else flags: {tids}")
    chk(tagged[0]["missing"] == [],
        f"a complete tagged entry must not be flagged: {tagged[0]['missing']}")
    chk(tagged[0]["title"] == "Tagged",
        f"the tag must not bleed into the title: {tagged[0]['title']!r}")

    # ---- per-domain parse -------------------------------------------------
    doms = pr.read_domain_decisions(vault)
    chk(sorted(doms) == ["mobile", "network", "systems"], f"domain files discovered: {sorted(doms)}")
    g3 = entry(doms["mobile"]["entries"], f"{MOB}-003")
    chk(g3 is not None and g3["missing"] == [], f"{MOB}-003 complete: {g3 and g3['missing']}")
    applied = pr.APPLIES_LINK_RE.findall(g3["fields"]["Applies to"])
    chk([n for _a, n in applied] == ["example-app", "example-widget"],
        f"nested Applies-to bullets must parse as one field: {applied}")

    # ---- symmetry ---------------------------------------------------------
    projs = {}
    for area, name in (("apps", "example-app"), ("apps", "example-client"),
                       ("tools", "orphan-proj")):
        projs[name] = pr.read_project_decisions(port / area / name)
    asym, unres = pr.decision_symmetry(projs, doms)
    blob = " | ".join(asym)
    ublob = " | ".join(unres)

    chk(f"{DEC}-007" not in blob,
        f"{DEC}-007 ↔ {MOB}-003 is symmetric and must not be flagged: {blob}")
    chk(any(f"{MOB}-011" in a and "example-app" in a for a in asym),
        f"one-sided Applies-to must be an asymmetry: {blob}")
    chk(any(f"{MOB}-009" in u for u in unres),
        f"link to a missing domain entry must be unresolved: {ublob}")
    chk(any("example-widget" in u for u in unres), f"example-widget must be unresolved: {ublob}")
    chk(any("example-viewer" in u for u in unres), f"example-viewer must be unresolved: {ublob}")
    chk(not any(f"{MOB}-009" in a for a in asym),
        "a missing target is unresolved, not an asymmetry")
    chk(any("defined in both" in u and f"{MOB}-003" in u for u in unres),
        f"a domain id defined in two domain files must be reported: {ublob}")
    # An Applies-to wikilink with no `<area>/` prefix matches neither direction of
    # the symmetry check, so the edge would silently not exist.
    chk(any("without an" in u and "example-viewer" in u for u in unres),
        f"unprefixed Applies-to link must be flagged, not dropped: {ublob}")
    # Resolving on the id alone would report a link that names the wrong register
    # file as correct.
    chk(any(f"{MOB}-011" in u and "links" in u and "but that entry lives in" in u
            for u in unres),
        f"a Global link naming the wrong domain file must be reported: {ublob}")

    dup = pr.read_project_decisions(port / "tools" / "dup-ids")
    chk(any("more than one block" in e and f"{DEC}-001" in e for e in dup["errors"]),
        f"a duplicate id within one register must be reported: {dup['errors']}")
    chk(len(dup["entries"]) == 2,
        "both blocks are still parsed — the duplicate is flagged, not dropped")

    mh_sym, mh_unres = pr.decision_symmetry({"malformed-headings": mh}, doms)
    chk(not any(" None " in a for a in mh_sym + mh_unres),
        f"a None id must never be interpolated into a report line: {mh_sym + mh_unres}")
    chk(any("malformed heading" in u and "fix the heading first" in u for u in mh_unres),
        f"malformed heading + Global link must be reported as unresolvable: {mh_unres}")

    projs_with_none = dict(projs)
    projs_with_none["example-widget"] = pr.read_project_decisions(port / "apps" / "example-widget")
    chk(projs_with_none["example-widget"] is None, "fixture sanity: example-widget has no register")
    try:
        pr.decision_symmetry(projs_with_none, doms)
    except Exception as exc:                                  # noqa: BLE001
        chk(False, f"None-valued project must degrade, not crash: {exc!r}")

    # ---- roll-up render ---------------------------------------------------
    reg = [{"area": "apps", "name": "example-app"},
           {"area": "apps", "name": "example-client"},
           {"area": "apps", "name": "malformed-headings"},
           {"area": "tools", "name": "orphan-proj"},
           {"area": "apps", "name": "example-widget"}]        # no decisions.md
    md = pr.render_global_decisions(vault, reg)

    for section in ("# Global Decisions", "## By domain", "## By project",
                    "## Asymmetries (review)", "## Unresolved targets"):
        chk(section in md, f"roll-up missing section {section!r}")

    chk("### mobile" in md and "### systems" in md, "each domain register needs a section")
    chk(f"**{MOB}-003** — Long work runs off the UI thread" in md, "domain entries must be listed")
    chk("apps/[[example-app]]" in md, "applies-to must render as an area-qualified wikilink")
    chk("| apps/[[example-app]] | 3" in md, f"per-project count row wrong:\n{md}")
    chk("| tools/[[orphan-proj]] | 1 | 1 | 0 | – |" in md,
        "a project with no domains renders an en-dash, not an empty cell")
    chk("example-widget" not in md.split("## Asymmetries")[0].split("## By project")[1],
        "a project with no decisions.md must not get a count row")

    chk("## Malformed entries (review)" in md, "roll-up needs a malformed-entry section")
    mal = md.split("## Malformed entries (review)")[1].split("## Asymmetries")[0]
    chk(f"{DEC}-005" in mal and "missing:" in mal,
        f"a block missing required fields must be named with what it lacks:\n{mal}")
    chk("malformed heading" in mal and "Hyphen instead of em-dash" in mal,
        f"a malformed heading must be named verbatim:\n{mal}")
    chk("duplicate field(s): Status" in mal, f"duplicate fields must be named:\n{mal}")
    chk(f"apps/[[example-app]] {DEC}-005" in mal,
        "each malformed entry must say which project it is in")

    tail = md.split("## Asymmetries (review)")[1]
    chk(f"{MOB}-011" in tail, f"asymmetry must be reported in the roll-up:\n{tail}")
    chk("defined in both" in tail, "id collision must be reported in the roll-up")
    chk("_None._" not in tail.split("## Unresolved targets")[0],
        "asymmetry section should not claim None when one exists")

    # ---- idempotency: write_if_changed must write once, not twice ---------
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "global-decisions.md"
        chk(pr.write_if_changed(target, md) is True, "first write must happen")
        chk(pr.write_if_changed(target, md) is False,
            "second identical write must be a no-op — rebuild idempotency guarantee")
        stamped = md.replace(f"**Last rebuilt:** {pr.TODAY}", "**Last rebuilt:** 2020-01-01")
        chk(pr.write_if_changed(target, stamped) is False,
            "a changed rebuild timestamp alone must NOT count as a change")

    # ---- sidecar pointer line ---------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        (repo / ".claude").mkdir(parents=True)
        vd = Path(td) / "vault"

        bare = vd / "Portfolio" / "x" / "bare"
        bare.mkdir(parents=True)
        pr.write_sidecar(repo, bare, vd, True)
        sc = (repo / ".claude" / "vault-context.md").read_text()
        chk("**Decisions:**" not in sc,
            "no decisions.md → no pointer line (a link to a missing file is worse than none)")
        chk("**Backlog:**" in sc, "unconditional pointers must still be written")

        withdec = vd / "Portfolio" / "x" / "withdec"
        withdec.mkdir(parents=True)
        (withdec / "decisions.md").write_text(f"# Decisions\n\n---\n\n## {DEC}-001 — t\n\n"
                                              "- **Decided:** 2026-01-01\n- **Status:** accepted\n"
                                              "- **Domains:** systems\n- **Source:** direct\n"
                                              "- **Reason:** because.\n")
        repo2 = Path(td) / "repo2"
        (repo2 / ".claude").mkdir(parents=True)
        pr.write_sidecar(repo2, withdec, vd, True)
        sc2 = (repo2 / ".claude" / "vault-context.md").read_text()
        line = [l for l in sc2.splitlines() if l.startswith("- **Decisions:**")]
        chk(len(line) == 1, f"exactly one Decisions pointer expected: {line}")
        chk(line and str(withdec / "decisions.md") in line[0], f"pointer must resolve: {line}")
        chk(line and not any(ch.isdigit() for ch in line[0].split("](")[0]),
            f"pointer-only: no count may be embedded: {line}")
        chk(pr.write_sidecar(repo2, withdec, vd, True) is False,
            "re-writing an unchanged sidecar must report no write")

    # ---- read-only guarantee ---------------------------------------------
    def tree_state():
        return sorted((str(p.relative_to(port)), p.stat().st_mtime_ns, p.stat().st_size)
                      for p in port.rglob("*") if p.is_file())

    before = tree_state()
    pr.render_global_decisions(vault, reg)
    pr.read_domain_decisions(vault)
    pr.decision_symmetry(projs, doms)
    chk(before == tree_state(),
        "the decisions rebuild path must never write into the vault registers")


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        vault = Path(td) / "vault"
        shutil.copytree(FIX, vault)
        expand_ids(vault)
        run(vault)
    shutil.rmtree(_HOME, ignore_errors=True)
    if fails:
        print("FAILURES:", file=sys.stderr)
        for f in fails:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("OK — decisions register: block parse, wrapped/nested fields, "
          "degrade-never-drop, both-direction symmetry, unresolved-vs-asymmetric "
          "split and read-only guarantee all verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
