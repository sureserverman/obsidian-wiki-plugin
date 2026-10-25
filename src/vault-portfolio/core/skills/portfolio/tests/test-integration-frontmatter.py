#!/usr/bin/env python3
"""An integration.md whose frontmatter cannot be read is refused, never read as "no edges".

Two scripts read the per-project integration.md: `portfolio-integrate.py` builds the
graph from it, and `portfolio-rebuild.py` renders each repo sidecar's Depends-on and
Impacts lines from it. A file that cannot be turned into edges (no frontmatter block,
YAML that does not parse, a top level that is not a mapping, an edge list that is
not a list, an edge that is neither a `"[[target]]"` string nor a mapping with a
string `target`) used to contribute nothing, silently: the project's edges vanished
from the graph and its sidecar, and the symmetry check then blamed its neighbours.

What this file pins, for both scripts, in a dry run and under --write:
  * the run exits non-zero and names the file and why;
  * under --write nothing is written — not the roll-ups, not a sidecar;
  * a vault whose integration.md files all parse runs clean (the refusal is not
    blanket);
  * both scripts read the file through one reader, portfolio-rebuild's
    read_integration() (one file) and read_integrations() (a run's files).

Throwaway HOME and temp vaults only. Stdlib + PyYAML, no pytest. Run:
  python3 -I src/vault-portfolio/core/skills/portfolio/tests/test-integration-frontmatter.py
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
INTEGRATE = SCRIPTS / "portfolio-integrate.py"
REBUILD = SCRIPTS / "portfolio-rebuild.py"

failures: list[str] = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        failures.append(name)
        print(f"FAIL  {name}  {str(detail)[:600]}")


GOOD_APP = ("---\nproject: example-app\nimpacts:\n  - target: \"[[example-cli]]\"\n"
            "    why: the cli reads the app's format\n---\n\n# integration\n")
GOOD_CLI = ("---\nproject: example-cli\ndepends_on:\n  - \"[[example-app]]\"\n---\n")

BAD = {
    "YAML that does not parse": "---\nproject: example-cli\ndepends_on: [\"[[example-app]]\"\n---\n",
    "no frontmatter block": "# integration\n\ndepends_on: [[example-app]]\n",
    "a top level that is not a mapping": "---\n- \"[[example-app]]\"\n---\n",
    "an edge list that is not a list": "---\ndepends_on: \"[[example-app]]\"\n---\n",
    "an edge that is neither a string nor a target mapping":
        "---\ndepends_on:\n  - why: no target here\n---\n",
}


def make_tree(root: Path, cli_text: str):
    vault = root / "vault"
    homes = {}
    repos = {}
    for name in ("example-app", "example-cli"):
        homes[name] = vault / "Portfolio" / "apps" / name
        homes[name].mkdir(parents=True)
        repos[name] = root / "repos" / name
        repos[name].mkdir(parents=True)
    (homes["example-app"] / "integration.md").write_text(GOOD_APP)
    (homes["example-cli"] / "integration.md").write_text(cli_text)
    reg = root / "registry.yaml"
    reg.write_text("projects:\n" + "".join(
        f"  - name: {n}\n    area: apps\n    path: {repos[n]}\n" for n in repos))
    home = root / "home"
    cfg = home / ".config" / "obsidian-wiki" / "config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"default_vault": str(vault), "registry": str(reg)}))
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    return vault, repos, homes, env


def state(*roots):
    return sorted((str(p), p.read_bytes() if p.is_file() else b"")
                  for r in roots for p in Path(r).rglob("*"))


def run(script, env, *args):
    return subprocess.run([sys.executable, "-I", str(script), *args],
                          capture_output=True, text=True, env=env, timeout=180)


# --------------------------------------------------------------------------
print("a clean vault runs clean (the refusal is not blanket):")
with tempfile.TemporaryDirectory() as td:
    vault, repos, homes, env = make_tree(Path(td), GOOD_CLI)
    r = run(INTEGRATE, env, "--write")
    check("integrate --write exits 0", r.returncode == 0, r.stdout + r.stderr)
    graph = vault / "Portfolio" / "integration-graph.md"
    check("...and renders both edge forms",
          graph.exists() and "`example-cli` → `example-app`" in graph.read_text(),
          graph.read_text() if graph.exists() else "no graph")
    r = run(REBUILD, env, "--write")
    check("rebuild --write exits 0", r.returncode == 0, r.stdout + r.stderr)
    side = repos["example-app"] / ".claude" / "vault-context.md"
    check("...and the sidecar carries the declared impact",
          side.exists() and "[[example-cli]]" in side.read_text())
    cli_side = repos["example-cli"] / ".claude" / "vault-context.md"
    check("...and a bare-string edge (`- \"[[example-app]]\"`) reaches the sidecar too",
          cli_side.exists() and "- **⬆ Depends on:** [[example-app]]\n" in cli_side.read_text(),
          cli_side.read_text() if cli_side.exists() else "no sidecar")

# --------------------------------------------------------------------------
print("integrate and rebuild read the same edges:")
MIXED = ("---\nproject: example-app\ndepends_on:\n  - \"[[example-cli]]\"\n"
         "  - target: \"[[example-lib]]\"\n    why: reads the lib's schema\n"
         "  - target: plain-target\n    why: a target written without brackets\n"
         "  - target: \"[[example-cfg]]\"\n    why:\n---\n")
WANT = [("example-cli", ""), ("example-lib", "reads the lib's schema"),
        ("plain-target", "a target written without brackets"), ("example-cfg", "")]
with tempfile.TemporaryDirectory() as td:
    vault, repos, homes, env = make_tree(Path(td), GOOD_CLI)
    (homes["example-app"] / "integration.md").write_text(MIXED)
    r = run(INTEGRATE, env, "--write")
    graph = (vault / "Portfolio" / "integration-graph.md").read_text()
    graph_edges = [ln for ln in graph.splitlines() if ln.startswith("- `example-app` → ")]
    check("integrate renders all four declared edges",
          r.returncode == 0 and graph_edges == [f"- `example-app` → `{t}`  — {w}" for t, w in WANT],
          "\n".join(graph_edges) + r.stderr)
    r = run(REBUILD, env, "--write")
    text = (repos["example-app"] / ".claude" / "vault-context.md").read_text()
    line = next((ln for ln in text.splitlines() if "⬆ Depends on:" in ln), "")
    want = "- **⬆ Depends on:** " + ", ".join(
        f"[[{t}]] ({w})" if w else f"[[{t}]]" for t, w in WANT)
    check("the sidecar lists the same four edges, in the same order", line == want,
          f"got  {line!r}\nwant {want!r}")

# --------------------------------------------------------------------------
for script in (INTEGRATE, REBUILD):
    print(f"{script.name} — an unreadable integration.md is refused:")
    for label, text in BAD.items():
        with tempfile.TemporaryDirectory() as td:
            vault, repos, homes, env = make_tree(Path(td), text)
            bad = homes["example-cli"] / "integration.md"
            for flags in ([], ["--write"]):
                mode = "--write" if flags else "dry run"
                before = state(vault, Path(td) / "repos")
                r = run(script, env, *flags)
                check(f"{label} ({mode}): exits non-zero naming the file",
                      r.returncode != 0 and str(bad) in r.stderr
                      and "Traceback" not in r.stderr,
                      f"rc={r.returncode} {r.stdout + r.stderr}")
                check(f"{label} ({mode}): nothing is written",
                      state(vault, Path(td) / "repos") == before)

# --------------------------------------------------------------------------
print("what still reads as a declaration:")
_spec = importlib.util.spec_from_file_location("rebuild_for_integration_test", REBUILD)
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)
with tempfile.TemporaryDirectory() as td:
    f = Path(td) / "integration.md"
    for label, raw, want in (
            ("CRLF line endings", GOOD_APP.replace("\n", "\r\n").encode(),
             {"project": "example-app"}),
            ("an empty frontmatter block (a leaf project)", b"---\n---\n\n# prose\n", {}),
            ("a leaf with both lists empty", b"---\ndepends_on: []\nimpacts:\n---\n", {})):
        f.write_bytes(raw)
        fm, why = pr.read_integration(f)
        check(f"{label} parses", why is None and fm is not None
              and all(fm.get(k) == v for k, v in want.items()), f"{fm!r} {why!r}")

# --------------------------------------------------------------------------
print("one reader for both scripts:")
for script in (INTEGRATE, REBUILD):
    tree = ast.parse(script.read_text(encoding="utf-8"))
    calls = {getattr(n.func, "attr", getattr(n.func, "id", "")) for n in ast.walk(tree)
             if isinstance(n, ast.Call)}
    loads = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "safe_load"]
    check(f"{script.name} reads integration.md through read_integration(s)()",
          calls & {"read_integration", "read_integrations"})
    if script is INTEGRATE:
        check("portfolio-integrate.py parses no YAML of its own", not loads, f"at {loads}")
        check("...and normalises edges through frontmatter_edges(), the sidecar's reader",
              "frontmatter_edges" in calls and "edge_targets" not in calls)

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("OK — an integration.md that cannot be read is refused by every reader")
