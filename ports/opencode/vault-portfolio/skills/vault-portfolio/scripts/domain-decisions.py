#!/usr/bin/env python3
"""domain-decisions — the per-domain half of the decisions register.

A domain register, `<vault>/Portfolio/decisions/<domain>.md`, holds the decisions
that bind every project on one platform or stack (`GDEC-<TAG>-NNN` entries; the
format is references/decisions-format.md). A project's own register is the other
half, and the planning plugin's per-repo digest reads it. This script answers the
domain questions:

  --list-domains            which domain registers exist, with entry counts
  --domains a,b             a digest of exactly those registers
  --infer-domains <repo>    which slugs a repo's files point at (domain-slugs.md)
  --promote <DEC-ID> --area A --name N --domain <slug> --reason "<generalized>"
                            lift a project decision into a domain register: a new
                            domain entry, plus both link directions
  --promote <DEC-ID> --area A --name N --global <GDEC-ID>
                            link a project decision to an existing domain entry
                            (`add --global` at creation time, or attaching a
                            further project): both link directions only

The digest has the per-repo digest's shape, so a caller reads both with one reader:
`extra` is a list of `{path, rows, errors}`, one per register, and each row carries
the same keys. Two more keys say what the digest could not cover:
`unknown_domains` (slugs asked for that have no register) and `available_domains`.

Properties this script exists to guarantee:

  * **Only what was asked.** `--domains` digests the named registers and no
    others; an unknown slug is reported, never silently empty: "no decisions bind
    this" and "you asked about a register that does not exist" are different
    answers, and conflating them is how a planner concludes nothing constrains them.
  * **Degrade, never drop.** A malformed block comes back flagged, a superseded
    one marked. The block grammar is portfolio-rebuild.py's, imported rather than
    re-derived, so the digest cannot disagree with the roll-up.
  * **Unreachable is not empty.** The vault comes from `_config.vault_setting()` and
    is checked by portfolio-rebuild.py's vault_problem(), the one definition of a
    reachable vault. An unset or unreachable vault is exit 2 with nothing on stdout.
  * **Both directions or neither.** `--promote` computes both edits first and
    refuses (exit 1, nothing written) when the project entry is absent, already
    carries a `Global:` line (re-promotion is a supersede), or the domain entry is
    absent or already lists the project. Every other byte of both files is kept.
  * **Writes participate in the maintenance protocol.** Without `--write`,
    `--promote` prints the edits and writes nothing. With it, the mirrored
    scripts/lib/vault_write_protocol.py require_write_access() runs before
    anything else, so another owner's maintenance window refuses the run.

Exit codes: 0 done · 1 a promote precondition does not hold (nothing written) ·
2 usage, config, an unreachable vault, or a write refused by a maintenance window.
"""
from __future__ import annotations

import argparse
import difflib
import fnmatch
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

_cspec = importlib.util.spec_from_file_location(
    "_vault_portfolio_config", Path(__file__).resolve().parent / "_config.py")
_config = importlib.util.module_from_spec(_cspec)
sys.modules[_cspec.name] = _config
_cspec.loader.exec_module(_config)

SLUG_TABLE = _config.PLUGIN_ROOT / "skills" / "vault-portfolio" / "references" / "domain-slugs.md"
REGISTER_DIR = Path("Portfolio/decisions")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TAG_RE = re.compile(r"^[A-Z]{2,5}$")
# A domain id's tag and number, and a header that records the tag before any entry
# exists (`GDEC-<TAG>-NNN`, written by new_register()).
DOMAIN_ID_PARTS_RE = re.compile(r"\bGDEC-([A-Z]+)-(\d+)\b")
HEADER_TAG_RE = re.compile(r"\bGDEC-([A-Z]+)-NNN\b")
# Trees that are a repo's dependencies, build output or test data, not its own stack.
# A fixture copying another stack's manifest would otherwise bind that stack's register.
SKIP_DIRS = {".git", "node_modules", "target", "build", "dist", "vendor", ".venv", "venv",
             "__pycache__", ".gradle", ".tox", "Pods",
             "tests", "test", "fixtures", "testdata", "__tests__"}
MAX_DEPTH = 8


class Refusal(Exception):
    """A promote precondition does not hold: exit 1, nothing written."""


class Usage(Exception):
    """Exit 2."""


_PR = None


def rebuild():
    """portfolio-rebuild.py as a module, loaded on first use.

    Reusing its parser is the point: the decisions block grammar, the
    degrade-never-drop contract and the required-field sets are fixture-locked by
    test-portfolio-decisions.py, and vault_problem() is the one definition of a
    reachable vault. A second implementation here would be a second thing to keep
    correct. Lazy, so infer_domains() needs no vault and no roll-up module.
    """
    global _PR
    if _PR is None:
        _PR = _config.load_module("skills/vault-portfolio/scripts/portfolio-rebuild.py")
    return _PR


# --- infer_domains ---------------------------------------------------------------

def slug_table(path=None):
    """[(patterns, slugs)] from the Files and slug columns of domain-slugs.md.

    Raises OSError when the table cannot be read and ValueError when it holds no
    rows: an empty table would otherwise read as "this repo touches no domain".
    """
    path = Path(path) if path else SLUG_TABLE
    rows, in_table = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")] \
            if line.lstrip().startswith("|") else None
        if cells is None:
            in_table = False
            continue
        if len(cells) == 3 and cells[1] == "Files":
            in_table = True
            continue
        if not in_table or len(cells) != 3 or set(cells[0]) <= {"-", ":"}:
            continue
        patterns = re.findall(r"`([^`]+)`", cells[1])
        slugs = [s for s in re.findall(r"`([^`]+)`", cells[2]) if SLUG_RE.match(s)]
        if patterns and slugs:
            rows.append((patterns, slugs))
    if not rows:
        raise ValueError(f"{path}: no Stack → domain rows with a Files column")
    return rows


def infer_domains(repo, table=None):
    """The domain slugs a repo's files point at, sorted and unique.

    Applies domain-slugs.md: each Files pattern is a glob over a file or directory
    name (or its repo-relative path, when the pattern holds a `/`), and a match adds
    that row's slugs. Dependency and build trees are skipped, and the walk stops at
    MAX_DEPTH levels. An empty list is a real answer (no file signal), not a failure.

    Raises NotADirectoryError when `repo` is not a directory, and OSError or
    ValueError when the table cannot be read or does not parse.
    """
    root = Path(repo)
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {repo}")
    rows = slug_table(table)
    found = set()
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        depth = len(rel_dir.parts)
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in dirnames + filenames:
            rel = (rel_dir / name).as_posix()
            for patterns, slugs in rows:
                if any(fnmatch.fnmatchcase(rel if "/" in p else name, p) for p in patterns):
                    found.update(slugs)
        if depth + 1 >= MAX_DEPTH:
            dirnames[:] = []
    return sorted(found)


# --- digest ----------------------------------------------------------------------

def first_sentence(text, limit=240):
    """The Reason's opening sentence — the constraint, without the full argument.

    A truncation mid-word is worse than a long line: the Reason IS the deliverable
    of an entry. So: cut at a sentence boundary when there is one in range,
    otherwise at a word boundary, and mark it.
    """
    t = " ".join((text or "").split())
    if not t:
        return ""
    for end in (". ", "; "):
        i = t.find(end)
        if 0 < i <= limit:
            return t[:i + 1].strip()
    if len(t) <= limit:
        return t
    return t[:t.rfind(" ", 0, limit)].rstrip(",;: ") + " …"


def digest_entry(entry, register):
    """One register block → one digest row, in the per-repo digest's row shape.

    Malformed blocks come through with `id: None` and a populated `missing` list;
    they are carried flagged rather than filtered, because a decision that fails to
    parse is exactly the one a planner must see.
    """
    f = entry["fields"]
    status = (f.get("Status") or "").strip()
    return {
        "id": entry["id"],
        "title": entry["title"],
        "status": status or "unknown",
        "superseded": status.lower().startswith("superseded"),
        "register": register,
        # `Applies to` is a nested bullet list that the shared parser flattens to
        # one string, leaving the "- " markers inline. Strip them for display.
        "applies_to": " ".join((f.get("Applies to", "") or "").split()).lstrip("- ").replace(" - ", "; "),
        "source": f.get("Source", ""),
        "decided": f.get("Decided", ""),
        "reason": first_sentence(f.get("Reason", "")),
        "malformed": entry["malformed_heading"] or bool(entry["missing"]),
        "missing": entry["missing"],
        "heading": entry["heading"],
    }


def list_domains(vault):
    """[(slug, entry_count, error_count)] for every domain register."""
    domains = rebuild().read_domain_decisions(vault)
    return [(slug, len(d["entries"]), len(d["errors"])) for slug, d in sorted(domains.items())]


def domain_digest(vault, slugs):
    """Digest of exactly the registers named by `slugs`, in the order asked.

    Superseded entries are INCLUDED and marked. "We used to believe X and stopped"
    is context a planner needs — dropping it invites re-proposing the approach that
    was already rejected.
    """
    domains = rebuild().read_domain_decisions(vault)
    extra, unknown = [], []
    for slug in slugs:
        d = domains.get(slug)
        if d is None:
            if slug not in unknown:
                unknown.append(slug)
            continue
        path = str(vault / REGISTER_DIR / f"{slug}.md")
        extra.append({"path": path,
                      "rows": [digest_entry(e, path) for e in d["entries"]],
                      "errors": list(d["errors"])})
    return {"extra": extra, "unknown_domains": unknown, "available_domains": sorted(domains)}


def _render_row(r):
    marks = []
    if r["superseded"]:
        marks.append("SUPERSEDED")
    if r["malformed"]:
        marks.append("MALFORMED: missing " + ", ".join(r["missing"]) if r["missing"]
                     else "MALFORMED: unparseable heading")
    mark = ("  [" + "; ".join(marks) + "]") if marks else ""
    ident = r["id"] or f"<unparseable heading: {r['heading']}>"
    print(f"{ident} — {r['title']}  ({r['status']}){mark}")
    if r["reason"]:
        print(f"    {r['reason']}")
    if r["applies_to"]:
        print(f"    applies to: {r['applies_to']}")


def render_text(result):
    """Human-readable digest, headed per register as the per-repo digest heads it."""
    if not result["extra"]:
        print("no decisions bind the requested domains")
    for reg in result["extra"]:
        print(f"# Decisions from {reg['path']} ({len(reg['rows'])})")
        for r in reg["rows"]:
            _render_row(r)
        for e in reg["errors"]:
            print(f"register error ({reg['path']}): {e}", file=sys.stderr)


# --- promote ---------------------------------------------------------------------

def _blocks(lines):
    """[(start, end, heading)] for every `## ` block, by line index (end exclusive)."""
    pr = rebuild()
    heads = [(i, m.group(1).strip()) for i, line in enumerate(lines)
             if (m := pr.BLOCK_HEAD_RE.match(line.rstrip("\r\n")))]
    return [(s, heads[k + 1][0] if k + 1 < len(heads) else len(lines), h)
            for k, (s, h) in enumerate(heads)]


def find_block(lines, id_re, want):
    """(start, end) of the one block whose heading id is `want`.

    Refuses an id claimed by two blocks: every reference to it is ambiguous, and
    writing into one of them would pick for the author.
    """
    hits = [(s, e) for s, e, h in _blocks(lines)
            if (m := id_re.match(h)) and m.group(1) == want]
    if len(hits) > 1:
        raise Refusal(f"{want} is defined by more than one block — fix the register first")
    return hits[0] if hits else None


def _is_content(line):
    s = line.strip()
    return bool(s) and not rebuild().RULE_RE.match(s)


def _end_of_content(lines, start, end):
    """Index just past the block's last content line (blank lines and rules excluded)."""
    last = start
    for i in range(start + 1, end):
        if _is_content(lines[i]):
            last = i
    return last + 1


def _insert(lines, at, new_lines):
    if at > 0 and not lines[at - 1].endswith("\n"):
        lines[at - 1] += "\n"
    lines[at:at] = new_lines


def _block_fields(lines, start, end, id_re, required):
    entry = rebuild().parse_decision_file("".join(lines[start:end]), id_re, required)
    return entry[0] if entry else None


def applies_line(area, name, why, dec_id):
    return f"  - {area}/[[{name}]] ({why}; {dec_id})\n"


def new_register(slug, tag):
    title = slug.replace("-", " ").capitalize()
    return (f"# {title} decisions\n\n"
            f"Cross-project decisions binding every project on the `{slug}` domain. "
            f"Ids: `GDEC-{tag}-NNN`.\n\n---\n")


def register_tag(text, slug, wanted):
    """The register's established tag, else the header's, else `wanted`, else derived."""
    tags = {m.group(1) for m in DOMAIN_ID_PARTS_RE.finditer(text)} if text else set()
    if len(tags) > 1:
        raise Refusal(f"{slug}.md mixes id tags {sorted(tags)} — fix the register first")
    hm = HEADER_TAG_RE.search(text or "")
    established = next(iter(tags), None) or (hm.group(1) if hm else None)
    if established and wanted and wanted != established:
        raise Refusal(f"{slug}.md keys its entries GDEC-{established}-…, not GDEC-{wanted}-…")
    tag = established or wanted or re.sub(r"[^a-z]", "", slug).upper()[:3]
    if not TAG_RE.match(tag):
        raise Usage(f"cannot derive an id tag from {slug!r}; pass --tag (2–5 capitals)")
    return tag


def require_vault_home(pr, area, name):
    """Refuse to derive <vault>/Portfolio/<area>/<name> for a registry entry that sets
    `records: repo`: that project has no vault home, and a folder at the derived path
    is not its register. No registry, or no entry by that area and name, derives the
    home as before. A registry that does not validate is a usage error."""
    try:
        registry = _config.registry_path()
    except _config.ConfigError as e:
        raise Usage(f"vault-portfolio config: {e}")
    if not registry.is_file():
        return
    projects, why = pr.registry_problem(registry)
    if why:
        raise Usage(f"project registry {registry} {why}")
    if any(p["area"] == area and p["name"] == name and pr.records_in_repo(p)
           for p in projects):
        raise Refusal(f"{area}/{name} sets {pr.OPTED_OUT} — pass --home with the folder "
                      f"that holds its decisions.md")


def plan_promote(vault, args):
    """(domain id, slug, [(path, old text or None, new text)]) for both files.

    Nothing is written here; every refusal is raised before main() writes anything.
    """
    pr = rebuild()
    dec_id = args.promote
    if not pr.DEC_ID_RE.match(f"{dec_id} — x"):
        raise Usage(f"--promote takes a project decision id, got {dec_id!r}")
    if not (args.area and args.name):
        raise Usage("--promote needs --area and --name (the project's registry entry)")
    if not (args.domain or args.domain_global):
        raise Usage("--promote needs --domain <slug> (a new domain entry) or --global <id>")
    if not args.home:
        require_vault_home(pr, args.area, args.name)
    home = Path(args.home) if args.home else vault / "Portfolio" / args.area / args.name
    proj_path = home / "decisions.md"
    if not proj_path.is_file():
        raise Refusal(f"{proj_path} does not exist — record the decision first")
    proj_text = proj_path.read_text(encoding="utf-8")
    proj_lines = proj_text.splitlines(keepends=True)
    span = find_block(proj_lines, pr.DEC_ID_RE, dec_id)
    if span is None:
        raise Refusal(f"{dec_id} is not in {proj_path}")
    entry = _block_fields(proj_lines, *span, pr.DEC_ID_RE, pr.PROJECT_REQUIRED)
    if "Global" in entry["fields"]:
        raise Refusal(f"{dec_id} already carries `Global: {entry['fields']['Global']}` — "
                      "re-promotion is a supersede, not a second promotion")
    why = " ".join((args.why or first_sentence(entry["fields"].get("Reason", ""), 100)
                    .rstrip(".")).split())
    if not why:
        raise Usage("no --why given and the entry has no Reason to condense")
    if not args.why and len(why) > 1 and why[1].islower():
        why = why[0].lower() + why[1:]
    add_applies = applies_line(args.area, args.name, why, dec_id)

    domains = pr.read_domain_decisions(vault)
    if args.domain_global:
        gid = args.domain_global
        owners = sorted(s for s, d in domains.items()
                        if any(e["id"] == gid for e in d["entries"]))
        if not owners:
            raise Refusal(f"{gid} is in no domain register")
        if len(owners) > 1:
            raise Refusal(f"{gid} is defined in {', '.join(owners)} — the target is ambiguous")
        slug = owners[0]
        if args.domain and args.domain != slug:
            raise Refusal(f"{gid} lives in {slug}.md, not {args.domain}.md")
        reg_path = vault / REGISTER_DIR / f"{slug}.md"
        reg_text = reg_path.read_text(encoding="utf-8")
        reg_lines = reg_text.splitlines(keepends=True)
        gspan = find_block(reg_lines, pr.GDEC_ID_RE, gid)
        gentry = _block_fields(reg_lines, *gspan, pr.GDEC_ID_RE, pr.DOMAIN_REQUIRED)
        listed = {n for _a, n in pr.APPLIES_LINK_RE.findall(gentry["fields"].get("Applies to", ""))}
        if args.name in listed:
            raise Refusal(f"{gid} already lists {args.name} under Applies to")
        s, e = gspan
        field_at = next((i for i in range(s + 1, e)
                         if (m := pr.FIELD_LINE_RE.match(reg_lines[i]))
                         and m.group(1).strip() == "Applies to"), None)
        if field_at is None:
            _insert(reg_lines, _end_of_content(reg_lines, s, e),
                    ["- **Applies to:**\n", add_applies])
        else:
            at = field_at + 1
            while at < e and _is_content(reg_lines[at]) and not pr.FIELD_LINE_RE.match(reg_lines[at]):
                at += 1
            _insert(reg_lines, at, [add_applies])
        reg_new, reg_old = "".join(reg_lines), reg_text
    else:
        slug = args.domain
        if not SLUG_RE.match(slug):
            raise Usage(f"--domain takes a lowercase slug, got {slug!r}")
        reason = " ".join((args.reason or "").split())
        if not reason:
            raise Usage("a new domain entry needs --reason: the constraint stated so it "
                        "holds for every project on the domain, not just this one")
        decided = entry["fields"].get("Decided", "").strip()
        if not decided:
            raise Refusal(f"{dec_id} has no Decided date to carry into the domain entry")
        reg_path = vault / REGISTER_DIR / f"{slug}.md"
        reg_old = reg_path.read_text(encoding="utf-8") if reg_path.is_file() else None
        tag = register_tag(reg_old, slug, args.tag)
        nums = [int(m.group(2)) for m in DOMAIN_ID_PARTS_RE.finditer(reg_old or "")
                if m.group(1) == tag]
        gid = f"GDEC-{tag}-{max(nums, default=0) + 1:03d}"
        title = " ".join((args.title or entry["title"]).split())
        block = (f"## {gid} — {title}\n\n"
                 f"- **Decided:** {decided}\n"
                 f"- **Status:** accepted\n"
                 f"- **Reason:** {reason}\n"
                 f"- **Applies to:**\n{add_applies}")
        base = reg_old if reg_old is not None else new_register(slug, tag)
        if not base.endswith("\n"):
            base += "\n"
        reg_new = base + ("" if base.endswith("\n\n") else "\n") + block

    _insert(proj_lines, _end_of_content(proj_lines, *span),
            [f"- **Global:** [[decisions/{slug}#{gid}]]\n"])
    return gid, slug, [(reg_path, reg_old, reg_new), (proj_path, proj_text, "".join(proj_lines))]


# --- main ------------------------------------------------------------------------

def resolve_vault():
    try:
        vault, source = _config.vault_setting()
    except _config.ConfigError as e:
        raise Usage(str(e))
    if vault is None:
        raise Usage("portfolio not configured: no vault is set (OBSIDIAN_VAULT_PATH, "
                    "`default_vault` in ~/.config/obsidian-wiki/config.json, or "
                    "`vault_dir` in ~/.claude/portfolio-config.yaml)")
    path, problem = rebuild().vault_problem(vault, source)
    if problem:
        raise Usage(problem)
    return path


def parser():
    ap = argparse.ArgumentParser(
        prog="domain-decisions",
        description="The per-domain decisions registers: list them, digest them, infer "
                    "which apply to a repo, and promote a project decision into one.",
        epilog="Exit codes: 0 done; 1 a promote precondition does not hold (nothing "
               "written); 2 usage, config, an unreachable vault, or a write refused by "
               "another owner's maintenance window. The vault is OBSIDIAN_VAULT_PATH, "
               "else obsidian-wiki's config.json default_vault, else the legacy "
               "portfolio-config.yaml vault_dir.")
    ap.add_argument("--list-domains", action="store_true",
                    help="list every domain register with its entry count")
    ap.add_argument("--domains", default="",
                    help="comma-separated slugs to digest (e.g. android,tor)")
    ap.add_argument("--infer-domains", metavar="REPO",
                    help="print the slugs domain-slugs.md infers from REPO's files")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    ap.add_argument("--promote", metavar="DEC-ID",
                    help="lift this project decision into a domain register")
    ap.add_argument("--area", default="", help="the project's registry area")
    ap.add_argument("--name", default="", help="the project's registry name")
    ap.add_argument("--home", default="",
                    help="the directory holding the project's decisions.md "
                         "(default <vault>/Portfolio/<area>/<name>; required for an "
                         "entry that sets `records: repo`)")
    ap.add_argument("--domain", default="", help="the domain slug of a new domain entry")
    ap.add_argument("--global", dest="domain_global", metavar="GDEC-ID", default="",
                    help="link to this existing domain entry instead of creating one")
    ap.add_argument("--reason", default="",
                    help="a new domain entry's Reason, generalized to every project on it")
    ap.add_argument("--title", default="", help="a new domain entry's title "
                                                "(default: the project entry's)")
    ap.add_argument("--tag", default="", help="a new register's id tag (default: derived)")
    ap.add_argument("--why", default="",
                    help="the Applies to note (default: the entry's Reason, condensed)")
    ap.add_argument("--write", action="store_true",
                    help="write the promotion (default: print the edits, write nothing)")
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.infer_domains:
            try:
                slugs = infer_domains(args.infer_domains)
            except (OSError, ValueError) as e:
                raise Usage(str(e))
            print(json.dumps(slugs) if args.format == "json" else "\n".join(slugs))
            return 0

        vault = resolve_vault()
        if args.write:
            # Before anything else, so another owner's window refuses the run
            # whatever it was asked to do.
            protocol = _config.load_module("scripts/lib/vault_write_protocol.py")
            try:
                protocol.require_write_access(vault)
            except protocol.ProtocolError as e:
                raise Usage(str(e))

        if args.list_domains:
            rows = list_domains(vault)
            if args.format == "json":
                print(json.dumps([{"domain": s, "entries": n, "errors": k,
                                   "path": str(vault / REGISTER_DIR / f"{s}.md")}
                                  for s, n, k in rows], indent=2))
            elif not rows:
                print(f"no domain registers found under {vault / REGISTER_DIR}")
            for s, n, k in (rows if args.format == "text" else []):
                print(f"{s}\t{n} entries" + (f"  ({k} malformed)" if k else ""))
            return 0

        if args.promote:
            gid, slug, edits = plan_promote(vault, args)
            verb = "wrote" if args.write else "would write"
            print(f"promote {args.promote} ({args.area}/{args.name}) → {gid} in {slug}.md")
            for path, old, new in edits:
                print(f"{verb} {path}")
                if not args.write:
                    sys.stdout.writelines(difflib.unified_diff(
                        (old or "").splitlines(keepends=True), new.splitlines(keepends=True),
                        fromfile=str(path) if old is not None else "/dev/null",
                        tofile=str(path)))
            if args.write:
                pr = rebuild()
                if not pr.vault_live(vault):
                    raise Usage(f"vault {vault} stopped being reachable — nothing written")
                for path, _old, new in edits:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    pr.atomic_write(path, new)
            return 0

        slugs = []
        for s in (x.strip().lower() for x in args.domains.split(",")):
            if s and s not in slugs:
                slugs.append(s)
        if not slugs:
            raise Usage("nothing to do: pass --list-domains, --domains <slug,...>, "
                        "--infer-domains <repo> or --promote <id>")
        result = domain_digest(vault, slugs)
        if args.format == "json":
            print(json.dumps(result, indent=2))
        else:
            render_text(result)
        for slug in result["unknown_domains"]:
            print(f"unknown domain: {slug} — available: "
                  f"{', '.join(result['available_domains']) or '(none)'}", file=sys.stderr)
        return 0
    except Refusal as e:
        print(f"domain-decisions: {e}", file=sys.stderr)
        return 1
    except Usage as e:
        print(f"domain-decisions: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
