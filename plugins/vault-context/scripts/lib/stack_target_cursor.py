#!/usr/bin/env python3
"""stack_target_cursor.py — write each applying stack page as a Cursor project rule.

Cursor does not read a global rules folder, so each project gets its own copy:
`<root>/.cursor/rules/vault-stack-<slug>.mdc`, where <root> is
`stack_pages.project_root(<project>)` — the git top level when the project is
inside a work tree, else the project folder. The session-start hook and the
sidecar match stacks from the same root. A rule is written only for a stack that
applies there (`stack_pages.applies` over `stack_pages.project_files(root)`):

    ---
    description: Owner rules for <slug> files (generated from the vault)
    globs: <the page's patterns, comma-joined>
    alwaysApply: false
    ---
    <!-- vault-context:stack-rule source=<slug> sha256=<sha256 of the page file> -->
    <the page body, byte for byte>

The marker line is sync-stack-rules.py's own (MARKER_RE, rule_text, read_marker
are taken from it). Globs are translated to what Cursor matches: a pattern with
no slash (`*.md`) matches at any depth in Claude Code, so it is written as
`**/*.md`; a `{a,b}` group is expanded into separate globs, since the list is
comma-separated; a leading `/` anchors a pattern holding another slash, which a
slash already does, so it is dropped. A top-level-only pattern with no other
slash (`/*.md`) has no Cursor form and the page is refused for this host (W
DEC-002); its existing rule, if any, is kept.

What is changed: only `vault-stack-<slug>.mdc` files that carry the marker for
their own slug directly after the frontmatter. A `vault-stack-*.mdc` without it
stops the run for that project, named and unchanged. No other file in
`.cursor/rules/` is read or touched. A rule whose stack no longer applies, or
whose page is gone, is removed. When no page at all is given yet generated rules
exist, nothing is removed (a half-mounted vault looks like that).

Per-project results, never an exception that stops a multi-project run:
  skipped  the folder is missing, or lib/eligibility.sh calls it an area
           directory (W DEC-001)
  refused  an unmarked vault-stack-*.mdc; or git would commit a rule: the root
           tracks something under .cursor (`git ls-files .cursor`), or
           `git check-ignore` does not ignore a rule path. Outside a git work
           tree there is nothing to commit, so the rules are written.
  error    a file-system error while applying
  ok       otherwise

Public API:
  plan(project, pages, refused=()) -> dict
      pages: iterable of (StackPage, sha256-hex of the page file) or StackPage
      refused: slugs whose page exists but was refused; their rules are kept
  apply(plan) -> dict      writes plan's actions; adds "counts"
  check(project, pages, refused=()) -> dict   adds "drift" and "in_sync"
  cursor_globs(patterns) -> str               raises ValueError
Every result holds "messages": lines for the owner, each naming the project or
file and the reason.

vault-context never writes to the vault (W DEC-003): pages are only read.
Stdlib only.
"""

import hashlib
import importlib.util
import os
import subprocess
import sys

sys.dont_write_bytecode = True

LIB = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(LIB)
if LIB not in sys.path:
    sys.path.insert(0, LIB)

from stack_pages import (  # noqa: E402
    StackPage, _expand_braces, applies, project_files, project_root,
)

RULE_PREFIX = "vault-stack-"
RULE_SUFFIX = ".mdc"
ELIGIBILITY = os.path.join(LIB, "eligibility.sh")
_SSR_NAME = "vault_context_sync_stack_rules"


def _ssr():
    """sync-stack-rules.py as a module: the one definition of the marker."""
    mod = sys.modules.get(_SSR_NAME)
    if mod is None:
        spec = importlib.util.spec_from_file_location(
            _SSR_NAME, os.path.join(SCRIPTS, "sync-stack-rules.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[_SSR_NAME] = mod
        try:
            spec.loader.exec_module(mod)
        except BaseException:
            del sys.modules[_SSR_NAME]
            raise
    return mod


def _marker(page, sha):
    """The marker line exactly as sync-stack-rules.py's rule_text writes it."""
    ssr = _ssr()
    lines = ssr.rule_text(page, sha).decode("utf-8").split("\n")
    marker = lines[lines.index("---", 1) + 1]
    if not ssr.MARKER_RE.match(marker):
        raise RuntimeError("sync-stack-rules.py rule_text no longer writes MARKER_RE")
    return marker


def cursor_globs(patterns):
    """The page's patterns as Cursor's comma-separated `globs:` value."""
    out = []
    for pat in patterns:
        for alt in _expand_braces(pat):
            if alt.startswith("/"):
                if "/" not in alt[1:]:
                    raise ValueError(
                        f"pattern {pat!r}: {alt!r} matches the top level only, "
                        "which a Cursor glob cannot say")
                alt = alt[1:]
            elif "/" not in alt:
                alt = "**/" + alt
            if alt not in out:
                out.append(alt)
    return ",".join(out)


def rule_text(page, sha):
    """The exact bytes a page's Cursor rule holds."""
    head = (f"---\ndescription: Owner rules for {page.stack} files (generated from the vault)\n"
            f"globs: {cursor_globs(page.paths)}\nalwaysApply: false\n---\n"
            f"{_marker(page, sha)}\n")
    return head.encode("utf-8") + page.body.encode("utf-8")


def _normalize_pages(pages):
    out = []
    for item in pages:
        if isinstance(item, StackPage):
            with open(item.path, "rb") as f:
                out.append((item, hashlib.sha256(f.read()).hexdigest()))
        else:
            page, sha = item
            out.append((page, sha))
    return out


def scan_rules(folder):
    """Generated rules by slug, and foreign vault-stack-*.mdc paths."""
    ours, foreign = {}, []
    if not os.path.isdir(folder):
        return ours, foreign
    read_marker = _ssr().read_marker
    for name in sorted(os.listdir(folder)):
        if not (name.startswith(RULE_PREFIX) and name.endswith(RULE_SUFFIX)):
            continue
        path = os.path.join(folder, name)
        slug = name[len(RULE_PREFIX):-len(RULE_SUFFIX)]
        mk = read_marker(path)
        if mk is None or mk[0] != slug:
            foreign.append(path)
        else:
            ours[slug] = path
    return ours, foreign


def _eligible(project):
    """(True, None) or (False, the area-directory text) via lib/eligibility.sh."""
    script = ('. "$1" || exit 2; if project_eligible "$2"; then exit 0; fi; '
              'area_directory_message "$2"; exit 3')
    try:
        res = subprocess.run(["bash", "-c", script, "_", ELIGIBILITY, project],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"vault-context: cannot run lib/eligibility.sh for {project}: {e}"
    if res.returncode == 0:
        return True, None
    text = (res.stdout + res.stderr).strip()
    if res.returncode != 3:
        text = (f"vault-context: lib/eligibility.sh failed for {project} "
                f"(exit {res.returncode}): {text or 'no output'}")
    return False, text


def _git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, timeout=30)


def _in_work_tree(root):
    try:
        res = _git(root, "rev-parse", "--is-inside-work-tree")
    except (OSError, subprocess.TimeoutExpired):
        return False
    return res.returncode == 0 and res.stdout.strip() == b"true"


def _commit_refusal(root, rel_paths):
    """A reason git would commit a rule under root, or None."""
    if not _in_work_tree(root):
        return None
    tracked = _git(root, "ls-files", "--", ".cursor")
    if tracked.returncode != 0:
        return (f"git ls-files failed in {root}: "
                f"{tracked.stderr.decode('utf-8', 'replace').strip()}")
    if tracked.stdout.strip():
        first = tracked.stdout.decode("utf-8", "replace").splitlines()[0]
        return (f"rules under {root}/.cursor would be committed: git tracks files there "
                f"({first}). Nothing was written; untrack .cursor/ and ignore it, then re-run")
    for rel in rel_paths:
        res = _git(root, "check-ignore", "-q", "--", rel)
        if res.returncode == 1:
            return (f"{os.path.join(root, rel)} would be committed: git does not ignore it. "
                    f"Nothing was written; add .cursor/ to {root}/.gitignore, then re-run")
        if res.returncode != 0:
            return (f"git check-ignore failed for {rel} in {root}: "
                    f"{res.stderr.decode('utf-8', 'replace').strip()}")
    return None


def _result(project, status, messages, root=None, rules_dir=None):
    return {"project": project, "root": root, "rules_dir": rules_dir, "status": status,
            "messages": list(messages), "actions": [], "errors": [], "foreign": []}


def plan(project, pages, refused=()):
    """What a sync would do in one project. Reads only; writes nothing."""
    project = os.path.abspath(os.fspath(project))
    tag = "cursor"
    if not os.path.isdir(project):
        return _result(project, "skipped",
                       [f"{tag}: skipped {project}: project folder is missing"])
    ok, text = _eligible(project)
    if not ok:
        first = text.splitlines()[0] if text else ""
        msgs = [f"{tag}: skipped {project}: area directory, not a project ({first})"]
        res = _result(project, "skipped", msgs)
        res["detail"] = text
        return res

    root = project_root(project)
    rules_dir = os.path.join(root, ".cursor", "rules")
    res = _result(project, "ok", [], root, rules_dir)

    ours, foreign = scan_rules(rules_dir)
    if foreign:
        res["status"] = "refused"
        res["foreign"] = foreign
        for f in foreign:
            res["messages"].append(
                f"{tag}: refusing {project}: {f} is named like a generated rule but has no "
                "vault-context marker for its slug; it was not touched, nothing was written")
        return res

    pages = _normalize_pages(pages)
    try:
        files = project_files(root)
    except OSError as e:
        res["status"] = "error"
        res["messages"].append(f"{tag}: cannot list files in {root}: {e}")
        return res

    keep = set(refused)
    given = set()
    actions = []
    for page, sha in pages:
        given.add(page.stack)
        rule = os.path.join(rules_dir, f"{RULE_PREFIX}{page.stack}{RULE_SUFFIX}")
        try:
            want = rule_text(page, sha)
        except ValueError as e:
            res["errors"].append({"slug": page.stack, "page": page.path, "reason": str(e)})
            res["messages"].append(f"{tag}: page refused for Cursor: {page.path}: {e}"
                                   + ("; its rule in " + rules_dir + " is kept"
                                      if page.stack in ours else ""))
            keep.add(page.stack)
            continue
        if applies(page, files):
            if page.stack not in ours:
                state = "missing"
            else:
                with open(ours[page.stack], "rb") as f:
                    state = "in-sync" if f.read() == want else "stale"
            actions.append({"slug": page.stack, "rule": rule, "state": state, "_want": want})
        elif page.stack in ours:
            actions.append({"slug": page.stack, "rule": rule, "state": "unused"})
    for slug, path in sorted(ours.items()):
        if slug not in given and slug not in keep:
            actions.append({"slug": slug, "rule": path, "state": "orphan"})

    if not pages and ours:
        res["status"] = "refused"
        res["messages"].append(
            f"{tag}: refusing {project}: no stack pages were given, yet {len(ours)} generated "
            f"rule(s) exist in {rules_dir}; removing none. Check that the vault is mounted")
        return res

    # Every rule that is or would be there is checked, in-sync ones too: a
    # project that stopped ignoring .cursor/ is reported, not silently kept.
    rels = [os.path.relpath(a["rule"], root) for a in actions if "_want" in a]
    if ours or rels:
        reason = _commit_refusal(root, rels)
        if reason:
            res["status"] = "refused"
            res["messages"].append(f"{tag}: refusing {project}: {reason}")
            return res

    res["actions"] = actions
    return res


def apply(plan_result):
    """Carry out a plan. Writes only marked rules; re-checks the marker first."""
    res = dict(plan_result)
    res["messages"] = list(plan_result.get("messages", []))
    counts = {"wrote": 0, "updated": 0, "removed": 0, "unchanged": 0}
    res["counts"] = counts
    if res.get("status") != "ok":
        return res
    ssr = _ssr()
    rules_dir = res["rules_dir"]
    done = []
    try:
        for a in res["actions"]:
            a = dict(a)
            state = a["state"]
            if state == "in-sync":
                counts["unchanged"] += 1
            elif state in ("missing", "stale"):
                if os.path.lexists(a["rule"]):
                    mk = ssr.read_marker(a["rule"])
                    if not (mk and mk[0] == a["slug"]):
                        res["status"] = "refused"
                        res["messages"].append(
                            f"cursor: refusing {res['project']}: {a['rule']} appeared without "
                            "the vault-context marker; it was not touched")
                        done.append(a)
                        continue
                os.makedirs(rules_dir, exist_ok=True)
                ssr.write_atomic(a["rule"], a["_want"])
                key = "wrote" if state == "missing" else "updated"
                counts[key] += 1
                a["action"] = key
            elif state in ("unused", "orphan"):
                mk = ssr.read_marker(a["rule"])
                if mk and mk[0] == a["slug"]:
                    os.unlink(a["rule"])
                    counts["removed"] += 1
                    a["action"] = "removed"
            done.append(a)
    except OSError as e:
        res["status"] = "error"
        res["messages"].append(
            f"cursor: file-system error in {res['project']}: {e.filename or rules_dir}: "
            f"{e.strerror or e}")
    res["actions"] = done + res["actions"][len(done):]
    if res["status"] in ("ok", "refused") and any(counts.values()):
        res["messages"].append(
            f"cursor rules in {rules_dir}: wrote {counts['wrote']}, updated {counts['updated']}, "
            f"removed {counts['removed']}, unchanged {counts['unchanged']}")
    return res


def check(project, pages, refused=()):
    """Compare only. "drift" lists every rule a sync would write, update or remove."""
    res = plan(project, pages, refused)
    drift = [{"slug": a["slug"], "state": a["state"], "rule": a["rule"]}
             for a in res["actions"] if a["state"] != "in-sync"]
    res["drift"] = drift
    res["in_sync"] = res["status"] == "ok" and not drift and not res["errors"]
    why = {"missing": "", "stale": "", "unused": " — its stack no longer applies; a sync removes it",
           "orphan": " — its page is gone; a sync removes it"}
    for d in drift:
        res["messages"].append(f"{d['state']}: {d['slug']} ({d['rule']}){why[d['state']]}")
    return res
