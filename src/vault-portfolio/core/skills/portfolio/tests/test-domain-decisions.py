#!/usr/bin/env python3
"""Fixture tests for the per-domain decisions half (domain-decisions.py).

Asserts the behaviours that make the domain digest trustworthy for a planner:

  * `--domains` digests ONLY the registers it was asked for, and an unknown slug
    is reported under `unknown_domains`, distinct from a domain that exists;
  * the digest has the per-repo decisions digest's shape (`extra` registers of
    `{path, rows, errors}`, rows with the same keys), so a caller reads both,
    and each row carries its entry's values (the Reason cut by first_sentence);
  * a block missing a required field, a block whose heading is not an id, and a
    superseded block all reach the digest, flagged or marked, never dropped;
  * an unconfigured or unreachable vault is exit 2 with nothing on stdout, never
    an empty digest ("nothing binds this" and "could not read" differ);
  * `infer_domains(repo)` applies domain-slugs.md to a repo's files: a Cargo
    repo is `rust`;
  * `--promote` writes both link directions (the domain entry's `Applies to`
    and the project entry's `Global`) and leaves every other byte alone; each
    refusal (an absent entry or domain entry, a `Global` line already present,
    `Global: none` included, a project already listed, an ambiguous id, a
    `--domain` naming another register, no Decided date, a bad slug) exits with
    its own stated reason, no traceback and no write; without `--write` it
    writes nothing; and under another owner's maintenance window any write,
    even a bare `--write`, is refused for the window and the vault is left
    unchanged.

Every case runs on a copy of the synthetic fixture vault under a throwaway HOME
with a scrubbed environment. Fixture ids are placeholders (`{DEC}-001`,
`{GDEC}-RS-001`), as fixtures/README.md describes: the copy step expands them.

Stdlib + PyYAML, no pytest. Run:
  python3 -I src/vault-portfolio/core/skills/portfolio/tests/test-domain-decisions.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "domain-decisions.py"
FIXV = HERE / "fixtures" / "domain-decisions" / "vault"
PROTOCOL = HERE.parents[2] / "scripts" / "lib" / "vault_write_protocol.py"
ID_PLACEHOLDERS = (("{GDEC}", "GDEC"), ("{DEC}", "DEC"), ("{BL}", "BL"))

# The row and register keys of the per-repo digest (decisions-relevant.py in the
# planning plugin). A caller reads both outputs with one reader, so the shapes match.
ROW_KEYS = {"id", "title", "status", "superseded", "register", "applies_to", "source",
            "decided", "reason", "malformed", "missing", "heading"}
REGISTER_KEYS = {"path", "rows", "errors"}

# Ids are spelled through these, as the fixtures spell them through placeholders.
DEC, GDEC = "DEC", "GDEC"

FAILS: list[str] = []


def expand_ids(text):
    for placeholder, prefix in ID_PLACEHOLDERS:
        text = text.replace(placeholder, prefix)
    return text


def check(cond, label):
    print(("  ok  " if cond else "  FAIL") + f"  {label}")
    if not cond:
        FAILS.append(label)


def tree_digest(root):
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def new_vault(tmp, name="vault"):
    dest = Path(tmp) / name
    shutil.copytree(FIXV, dest)
    for p in dest.rglob("*.md"):
        p.write_text(expand_ids(p.read_text()))
    home = Path(tmp) / f"{name}-home"
    home.mkdir()
    return dest, home


def run(home, *args, vault=None, **extra):
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    if vault is not None:
        env["OBSIDIAN_VAULT_PATH"] = str(vault)
    env.update({k: str(v) for k, v in extra.items()})
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True, env=env)


def as_json(p, label):
    try:
        return json.loads(p.stdout)
    except ValueError:
        check(False, f"{label}: stdout is JSON (rc {p.returncode}, stderr {p.stderr.strip()[:200]!r})")
        return None


def load_script():
    spec = importlib.util.spec_from_file_location("domain_decisions_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_digest(tmp):
    print("[digest: only the requested slugs]")
    vault, home = new_vault(tmp)
    rust = str(vault / "Portfolio/decisions/rust.md")

    p = run(home, "--domains", "rust", "--format", "json", vault=vault)
    d = as_json(p, "--domains rust")
    if d is None:
        return
    check(p.returncode == 0, f"--domains rust exits 0 (rc {p.returncode})")
    check([r["path"] for r in d.get("extra", [])] == [rust],
          f"exactly the rust register is digested ({[r['path'] for r in d.get('extra', [])]})")
    rows = [row for reg in d.get("extra", []) for row in reg["rows"]]
    check(sorted(str(r["id"]) for r in rows) == [f"{GDEC}-RS-001", f"{GDEC}-RS-002"],
          f"only rust entries are listed ({sorted(str(r['id']) for r in rows)})")
    check(all(r["register"] == rust for r in rows), "every row names the rust register")
    check(d.get("unknown_domains") == [], "no unknown domains for a known slug")

    print("[digest: shape matches the per-repo digest]")
    check(all(set(reg) == REGISTER_KEYS for reg in d["extra"]),
          f"each register is {sorted(REGISTER_KEYS)} ({[sorted(reg) for reg in d['extra']]})")
    check(rows and all(set(r) == ROW_KEYS for r in rows),
          f"each row has the per-repo row keys ({sorted(rows[0]) if rows else None})")
    rs2 = next((r for r in rows if r["id"] == f"{GDEC}-RS-002"), None)
    check(rs2 is not None and rs2["superseded"] is True,
          "a superseded entry is included and marked, not filtered")

    print("[digest: row values]")
    rs1 = next((r for r in rows if r["id"] == f"{GDEC}-RS-001"), None) or {}
    want = {
        "title": "Release builds pin the toolchain",
        "status": "accepted",
        "superseded": False,
        "register": rust,
        "decided": "2026-03-01",
        # The Reason's first sentence, its wrapped lines joined.
        "reason": "An unpinned toolchain changed lint output between two release builds "
                  "of the same commit.",
        # The nested bullet comes through without its "- " marker.
        "applies_to": f"apps/[[example-app]] (ships release builds; {DEC}-001)",
        # A domain entry carries no Source field, so the row's source is empty.
        "source": "",
        "malformed": False,
        "missing": [],
    }
    got = {k: rs1.get(k) for k in want}
    check(got == want, f"{GDEC}-RS-001's row carries its field values "
                       f"({ {k: v for k, v in got.items() if v != want[k]} })")
    check(rs2 is not None and rs2["status"] == f"superseded by {GDEC}-RS-001"
          and rs2["reason"] == "Offline builds needed every crate on disk.",
          f"the superseded row keeps its status text and its own reason ({rs2})")
    p = run(home, "--domains", "android", "--format", "json", vault=vault)
    a = as_json(p, "--domains android")
    arows = [row for reg in (a or {}).get("extra", []) for row in reg["rows"]]
    check([(r["id"], r["source"], r["applies_to"]) for r in arows]
          == [(f"{GDEC}-AND-001", "code review",
               f"apps/[[example-mobile]] (talks to the network; {DEC}-004)")],
          f"a domain entry's Source reaches the row's source ({arows})")

    print("[digest: unknown slug]")
    p = run(home, "--domains", "rust,nosuchdomain", "--format", "json", vault=vault)
    u = as_json(p, "--domains rust,nosuchdomain")
    if u is None:
        return
    check(u.get("unknown_domains") == ["nosuchdomain"],
          f"an unknown slug is reported under unknown_domains ({u.get('unknown_domains')})")
    check([r["path"] for r in u["extra"]] == [rust],
          "an unknown slug adds no register and the known one is still digested")
    check(u.get("available_domains") == ["android", "malformed", "rust"],
          f"the report offers the slugs that exist ({u.get('available_domains')})")
    check("unknown domain: nosuchdomain" in p.stderr, "and says so on stderr")

    print("[digest: degrade, never drop]")
    p = run(home, "--domains", "malformed", "--format", "json", vault=vault)
    m = as_json(p, "--domains malformed")
    if m is None:
        return
    mrows = m["extra"][0]["rows"] if m.get("extra") else []
    check(len(mrows) == 3, f"all three malformed-register blocks reach the digest ({len(mrows)})")
    no_reason = next((r for r in mrows if r["id"] == f"{GDEC}-MAL-001"), None)
    check(no_reason is not None and no_reason["malformed"] and "Reason" in no_reason["missing"],
          "a block missing Reason is flagged and names the field")
    bad_head = [r for r in mrows if r["id"] is None]
    check(len(bad_head) == 1 and bad_head[0]["malformed"]
          and "not a GDEC id" in bad_head[0]["heading"],
          "a non-id heading is flagged and keeps its raw heading for repair")

    print("[digest: text form]")
    p = run(home, "--domains", "rust", vault=vault)
    check(p.returncode == 0 and f"# Decisions from {rust} (2)" in p.stdout,
          "text output heads each register the way the per-repo digest does")

    print("[list-domains]")
    p = run(home, "--list-domains", "--format", "json", vault=vault)
    lst = as_json(p, "--list-domains")
    if lst is not None:
        counts = {r["domain"]: r["entries"] for r in lst}
        check(counts == {"android": 1, "malformed": 3, "rust": 2},
              f"every domain register is listed with its entry count ({counts})")
    p = run(home, "--list-domains", vault=vault)
    check(p.returncode == 0 and "rust\t2 entries" in p.stdout, "text --list-domains")


def test_refusals(tmp):
    print("[unconfigured / unreachable / usage]")
    home = Path(tmp) / "empty-home"
    home.mkdir()
    p = run(home, "--domains", "rust")
    check(p.returncode == 2 and p.stdout == "",
          f"no vault configured: exit 2, nothing on stdout (rc {p.returncode})")
    check("not configured" in p.stderr, f"and says so ({p.stderr.strip()[:120]!r})")
    hollow = Path(tmp) / "hollow"
    hollow.mkdir()
    p = run(home, "--list-domains", vault=hollow)
    check(p.returncode == 2 and p.stdout == "",
          "a vault with no Portfolio/ is unreachable: exit 2, never an empty list")
    check("unreachable" in p.stderr, "and says why")
    vault, vhome = new_vault(tmp)
    p = run(vhome, vault=vault)
    check(p.returncode == 2, "nothing to do is a usage error")


def test_first_sentence(tmp):
    print("[first_sentence]")
    dd = load_script()
    fs = dd.first_sentence
    check(fs("One. Two.") == "One.", f"cuts at the first sentence ({fs('One. Two.')!r})")
    semi = fs("First clause; second clause")
    check(semi == "First clause;", f"with no '. ' in range, a '; ' boundary cuts ({semi!r})")
    long = "w" * 400
    check(fs(long).endswith("…"), f"over-long text is marked as elided ({fs(long)[-6:]!r})")
    # 8 characters a word, so the limit of 100 falls inside the 13th word.
    words = " ".join(["toolkit"] * 40)
    cut = fs(words, 100)
    check(cut.endswith(" …") and len(cut) <= 102 and cut[:-2].split(" ") == ["toolkit"] * 12,
          f"with no boundary in range, it cuts at a word and marks it ({cut!r})")
    check(fs("Short and whole") == "Short and whole", "text within the limit is kept whole")
    spaced = fs("a\n\n   b")
    check(spaced == "a b", f"whitespace is collapsed ({spaced!r})")
    check(fs("") == "" and fs(None) == "" and fs("  \n ") == "", "empty text stays empty")


def test_infer_domains(tmp):
    print("[infer_domains]")
    dd = load_script()
    cargo = Path(tmp) / "cargo-repo"
    (cargo / "src").mkdir(parents=True)
    (cargo / "Cargo.toml").write_text('[package]\nname = "x"\n')
    (cargo / "src" / "main.rs").write_text("fn main() {}\n")
    got = dd.infer_domains(cargo)
    check(got == ["rust"], f"a Cargo repo infers rust ({got!r})")

    mixed = Path(tmp) / "mixed-repo"
    (mixed / ".github" / "workflows").mkdir(parents=True)
    (mixed / "settings.gradle.kts").write_text("")
    (mixed / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
    got = dd.infer_domains(mixed)
    check(got == ["android", "ci"], f"signals combine, sorted ({got!r})")

    bare = Path(tmp) / "bare-repo"
    (bare / "node_modules" / "dep").mkdir(parents=True)
    (bare / "node_modules" / "dep" / "Cargo.toml").write_text("")
    (bare / "README.md").write_text("x\n")
    got = dd.infer_domains(bare)
    check(got == [], f"no signal, and dependency trees are not the repo's stack ({got!r})")

    # A test fixture copying another stack's manifest is test data, not the
    # repo's stack: a WebExtension fixture must not bind a Python tool to the
    # browser-extensions register.
    fx = Path(tmp) / "fixture-repo"
    for d in ("tests/fixtures/chrome", "test/data", "pkg/testdata", "web/__tests__"):
        (fx / d).mkdir(parents=True)
    (fx / "tests" / "fixtures" / "chrome" / "manifest.json").write_text("{}\n")
    (fx / "test" / "data" / "Cargo.toml").write_text("")
    (fx / "pkg" / "testdata" / "torrc").write_text("")
    (fx / "web" / "__tests__" / "AndroidManifest.xml").write_text("")
    (fx / "main.py").write_text("print(1)\n")
    got = dd.infer_domains(fx)
    check(got == [], f"test and fixture trees are not the repo's stack ({got!r})")

    home = Path(tmp) / "infer-home"
    home.mkdir()
    p = run(home, "--infer-domains", cargo)
    check(p.returncode == 0 and p.stdout.split() == ["rust"],
          f"--infer-domains prints the slugs without needing a vault ({p.stdout!r}, rc {p.returncode})")


def symmetric(dd, vault, gid, project):
    pr = dd.rebuild()
    proj = {}
    for home in (vault / "Portfolio" / "apps").iterdir():
        proj[home.name] = pr.read_project_decisions(home)
    asym, unresolved = pr.decision_symmetry(proj, pr.read_domain_decisions(vault))
    hits = [m for m in asym + unresolved if gid in m and project in m]
    return hits


def without(text, added):
    lines = text.splitlines(keepends=True)
    for a in added:
        lines.remove(a)
    return "".join(lines)


def test_promote(tmp):
    dd = load_script()
    print("[promote: dry run writes nothing]")
    vault, home = new_vault(tmp, "dry")
    before = tree_digest(vault)
    p = run(home, "--promote", f"{DEC}-002", "--area", "apps", "--name", "example-app",
            "--domain", "rust", "--reason", "Callers match on a stable code.", vault=vault)
    check(p.returncode == 0 and f"{GDEC}-RS-003" in p.stdout,
          f"dry run names the entry it would create (rc {p.returncode}, {p.stderr.strip()[:160]!r})")
    check(tree_digest(vault) == before, "dry run leaves the vault unchanged")

    print("[promote: into an existing register]")
    vault, home = new_vault(tmp, "into")
    proj_file = vault / "Portfolio" / "apps" / "example-app" / "decisions.md"
    rust_file = vault / "Portfolio/decisions/rust.md"
    proj_before, rust_before = proj_file.read_text(), rust_file.read_text()
    p = run(home, "--promote", f"{DEC}-002", "--area", "apps", "--name", "example-app",
            "--domain", "rust", "--reason", "Callers match on a stable code, never on text.",
            "--why", "callers match on codes", "--write", vault=vault)
    check(p.returncode == 0, f"promote --write exits 0 (rc {p.returncode}, {p.stderr.strip()[:200]!r})")
    rust_after, proj_after = rust_file.read_text(), proj_file.read_text()
    check(rust_after.startswith(rust_before.rstrip("\n")),
          "the domain register keeps every existing byte; the new block is appended")
    check(f"## {GDEC}-RS-003 — Errors carry a stable code" in rust_after,
          "the next id is max + 1 in the register's own tag")
    check(f"  - apps/[[example-app]] (callers match on codes; {DEC}-002)" in rust_after,
          "Applies to names the project, its why and its decision")
    link = f"- **Global:** [[decisions/rust#{GDEC}-RS-003]]\n"
    check(link in proj_after, "the project entry gains the Global link")
    check(link in proj_after and without(proj_after, [link]) == proj_before,
          "and nothing else in the project register changes")
    head = f"## {DEC}-002"
    sec = proj_after.split(head, 1)[1].split("\n## ", 1)[0] if head in proj_after else ""
    check(link in sec, "the Global link lands inside the promoted entry's own block")
    check(symmetric(dd, vault, f"{GDEC}-RS-003", "example-app") == [],
          "the roll-up's symmetry check finds both directions")
    # Negative control: drop the Global line again and the same check must see the
    # one-sided Applies to, or its empty answer above proves nothing.
    proj_file.write_text(without(proj_after, [link]))
    check(symmetric(dd, vault, f"{GDEC}-RS-003", "example-app") != [],
          "with one direction removed, the symmetry check reports it")

    print("[promote: a new domain register]")
    vault, home = new_vault(tmp, "fresh")
    p = run(home, "--promote", f"{DEC}-002", "--area", "apps", "--name", "example-app",
            "--domain", "web", "--tag", "WEB", "--reason", "Callers match on codes.",
            "--write", vault=vault)
    web = vault / "Portfolio/decisions/web.md"
    check(p.returncode == 0 and web.is_file(), f"a missing register is created (rc {p.returncode})")
    text = web.read_text() if web.is_file() else ""
    check(f"## {GDEC}-WEB-001 — " in text and f"{GDEC}-WEB-NNN" in text,
          "it starts at 001 and records its tag in the header")
    # No --why: the note is the Reason's first sentence (limit 100), its final
    # period dropped and its first letter lowered.
    check(f"- **Applies to:**\n  - apps/[[example-app]] (callers matched on message text, "
          f"which broke on every rewording; {DEC}-002)\n" in text,
          f"without --why, Applies to condenses the entry's Reason ({text[-160:]!r})")
    check(symmetric(dd, vault, f"{GDEC}-WEB-001", "example-app") == [],
          "and the two directions are symmetric")

    print("[promote --global: attach a further project]")
    vault, home = new_vault(tmp, "link")
    lib_file = vault / "Portfolio" / "apps" / "example-lib" / "decisions.md"
    rust_file = vault / "Portfolio/decisions/rust.md"
    lib_before, rust_before = lib_file.read_text(), rust_file.read_text()
    p = run(home, "--promote", f"{DEC}-001", "--area", "apps", "--name", "example-lib",
            "--global", f"{GDEC}-RS-001", "--why", "built by the same release job",
            "--write", vault=vault)
    check(p.returncode == 0, f"link --write exits 0 (rc {p.returncode}, {p.stderr.strip()[:200]!r})")
    applies = f"  - apps/[[example-lib]] (built by the same release job; {DEC}-001)\n"
    glink = f"- **Global:** [[decisions/rust#{GDEC}-RS-001]]\n"
    rust_after = rust_file.read_text()
    check(applies in rust_after and without(rust_after, [applies]) == rust_before,
          "only the Applies to line is added to the domain register")
    check(rust_after.index(applies) < rust_after.index(f"## {GDEC}-RS-002"),
          f"inside {GDEC}-RS-001's block, not the next one")
    lib_after = lib_file.read_text()
    check(glink in lib_after and without(lib_after, [glink]) == lib_before,
          "only the Global line is added to the project register")
    check(not (vault / "Portfolio/decisions/rust.md.tmp").exists()
          and len(list((vault / "Portfolio/decisions").glob(".*"))) == 0,
          "no temp file is left beside the register")
    check(symmetric(dd, vault, f"{GDEC}-RS-001", "example-lib") == [],
          "the symmetry check finds both directions")

    print("[promote: refusals write nothing]")
    vault, home = new_vault(tmp, "refuse")
    # Two shapes the shared fixture does not hold, added to this copy only: a
    # second register defining {GDEC}-RS-002, and a project entry with no Decided.
    (vault / "Portfolio/decisions/rust-copy.md").write_text(
        "# Rust copy decisions\n\n---\n\n"
        f"## {GDEC}-RS-002 — The same id in a second register\n\n"
        "- **Decided:** 2026-03-02\n- **Status:** accepted\n"
        "- **Reason:** Copied by mistake.\n- **Applies to:**\n"
        f"  - apps/[[example-lib]] (copied; {DEC}-001)\n")
    undated = vault / "Portfolio/apps/example-undated"
    undated.mkdir()
    (undated / "decisions.md").write_text(
        "# Decisions\n\n---\n\n"
        f"## {DEC}-001 — An entry with no date\n\n"
        "- **Status:** accepted\n- **Domains:** rust\n- **Source:** direct\n"
        "- **Reason:** The date was never written down.\n")
    before = tree_digest(vault)
    app, lib = ["--name", "example-app"], ["--name", "example-lib"]
    new_rust = ["--domain", "rust", "--reason", "x"]
    cases = [
        # (args, label, exit code, the reason stderr must give)
        ([f"{DEC}-001", *app, *new_rust], "a linked entry", 1,
         f"{DEC}-001 already carries `Global: [[decisions/rust#{GDEC}-RS-001]]`"),
        # `Global: none` says promotion was considered and declined. The script
        # reads any Global field as already decided, so it refuses the same way.
        ([f"{DEC}-003", *app, *new_rust], "a `Global: none` entry", 1,
         f"{DEC}-003 already carries `Global: none — project-local, promotion considered`"),
        ([f"{DEC}-099", *app, *new_rust], "an absent entry", 1,
         f"{DEC}-099 is not in "),
        ([f"{DEC}-002", *app, "--global", f"{GDEC}-RS-099"], "an absent domain entry", 1,
         f"{GDEC}-RS-099 is in no domain register"),
        ([f"{DEC}-002", *app, "--global", f"{GDEC}-RS-001"], "a project already listed", 1,
         f"{GDEC}-RS-001 already lists example-app under Applies to"),
        ([f"{DEC}-001", *lib, "--global", f"{GDEC}-RS-002"], "an id in two registers", 1,
         f"{GDEC}-RS-002 is defined in rust, rust-copy — the target is ambiguous"),
        ([f"{DEC}-001", *lib, "--global", f"{GDEC}-AND-001", "--domain", "rust"],
         "--domain naming another register", 1,
         f"{GDEC}-AND-001 lives in android.md, not rust.md"),
        ([f"{DEC}-001", "--name", "example-undated", *new_rust], "an entry with no Decided", 1,
         f"{DEC}-001 has no Decided date"),
        ([f"{DEC}-002", *app, "--domain", "Rust_Lang", "--reason", "x"], "a bad slug", 2,
         "--domain takes a lowercase slug, got 'Rust_Lang'"),
        ([f"{DEC}-002", *app, "--domain", "rust"], "a new domain entry without --reason", 2,
         "a new domain entry needs --reason"),
    ]
    for args, label, rc, reason in cases:
        case_before = tree_digest(vault)
        p = run(home, "--promote", *args, "--area", "apps", "--write", vault=vault)
        check(p.returncode == rc and f"domain-decisions: {reason}" in p.stderr
              and "Traceback" not in p.stderr and p.stdout == ""
              and tree_digest(vault) == case_before,
              f"{label}: exit {rc}, says {reason!r}, writes nothing "
              f"(rc {p.returncode}, {p.stderr.strip()[-200:]!r})")
    check(tree_digest(vault) == before, "no refusal wrote anything")


def test_maintenance(tmp):
    print("[maintenance window]")
    spec = importlib.util.spec_from_file_location("vwp_under_test", PROTOCOL)
    vwp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vwp)
    vault, home = new_vault(tmp, "held")
    window = vwp.start(vault.resolve(), "someone-else", "maintenance", 600)
    before = tree_digest(vault)
    args = ["--promote", f"{DEC}-002", "--area", "apps", "--name", "example-app",
            "--domain", "rust", "--reason", "Callers match on codes.", "--write"]
    p = run(home, *args, vault=vault)
    check(p.returncode != 0, f"a foreign window refuses the write (rc {p.returncode})")
    check("maintenance" in p.stderr, f"and says why ({p.stderr.strip()[:160]!r})")
    check(tree_digest(vault) == before, "the vault is unchanged under a foreign window")
    # The window is checked before the request is read, so a bare --write is refused
    # for the window, not reported as having nothing to do.
    p = run(home, "--write", vault=vault)
    check(p.returncode == 2 and "maintenance" in p.stderr and "nothing to do" not in p.stderr
          and tree_digest(vault) == before,
          f"a bare --write is refused for the window first (rc {p.returncode}, "
          f"{p.stderr.strip()[:160]!r})")
    p = run(home, *args, vault=vault, OBSIDIAN_WIKI_MAINTENANCE_TOKEN=window["token"])
    check(p.returncode == 0 and tree_digest(vault) != before,
          f"the window's own owner may write (rc {p.returncode}, {p.stderr.strip()[:160]!r})")
    p = run(home, "--domains", "rust", vault=vault)
    check(p.returncode == 0, "reading is never gated by a window")


def main():
    for test in (test_digest, test_refusals, test_first_sentence, test_infer_domains,
                 test_promote, test_maintenance):
        with tempfile.TemporaryDirectory() as td:
            try:
                test(td)
            except Exception as e:  # a crashed case is a failure, never a skip
                check(False, f"{test.__name__} raised {type(e).__name__}: {e}")
    if FAILS:
        print(f"\nFAILED — {len(FAILS)} check(s):")
        for f in FAILS:
            print(f"  - {f}")
        sys.exit(1)
    print("\nOK — all domain-decisions checks passed")


if __name__ == "__main__":
    main()
