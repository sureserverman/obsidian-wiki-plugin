#!/usr/bin/env python3
"""stack_target_codex.py — deliver the vault's stack pages to Codex.

Codex has no glob-scoped rules, and its home AGENTS file loads in full in every
session, capped with the rest of the project docs at 32 KiB by default. So
Codex gets a pointer, not the pages:

  Copies  <codex-home>/vault-stacks/<slug>.md — the marker line, then the page
          body byte for byte. The marker is the one sync-stack-rules.py writes
          (its MARKER_RE), here on line 1 because a copy has no frontmatter:

              <!-- vault-context:stack-rule source=<slug> sha256=<sha256 of the page file> -->

  Block   one block in the home AGENTS file, between two comment lines:

              <!-- vault-context:stacks:start -->
              ## Stack rules

              Before you read or edit a file that matches a pattern below, read the page next to it and follow it.

              - `**/*.rs`, `**/Cargo.toml` - <codex-home>/vault-stacks/rust.md
              <!-- vault-context:stacks:end -->

The block goes into AGENTS.override.md when that file exists and is not empty
(after stripping whitespace), else into AGENTS.md: Codex reads only the first
non-empty one of the two at the home level. A block found in the other file is
moved. Every byte outside the block is kept. Inserting into a file that does
not end in a newline adds one newline before the start marker; that is the
only byte the tool ever adds outside the block.

This module writes only inside the Codex home: never a project's AGENTS file,
never anything under ~/.agents/.

What it refuses (W DEC-002), raising CodexTargetError naming each file and
why, before anything is written:
  - an AGENTS file with a start marker and no end marker, an end marker and no
    start marker, an end before its start, two blocks, or a marker on a line
    with other text (a CRLF line included)
  - an AGENTS file that is a symlink or not a regular file (replacing it would
    cut the link)
  - a `*.md` in vault-stacks/ that is not a regular file whose line 1 is the
    marker naming its own slug; other files there are never read
  - a page pattern holding a backtick (it would break the pointer line)

Removal. With no pages the block is removed from both files and every marked
copy goes. An AGENTS.md left holding zero bytes once the block is out is one
this tool created (it writes a new AGENTS.md as the block and its newline,
nothing else), so it is deleted. Any byte left — owner text, even a blank
line — keeps the file. AGENTS.override.md is never created, so never deleted.
Guarding against a half-mounted vault that shows no pages is the caller's job
(sync-stack-rules.py stops before it would remove every copy).

Public API:
  resolve_codex_home(arg=None) -> str        arg, else $CODEX_HOME, else ~/.codex
  plan(codex_home, pages) -> CodexPlan       raises CodexTargetError
  apply(plan) -> dict                        raises CodexTargetError, OSError
  check(codex_home, pages) -> dict           raises CodexTargetError

`pages` holds stack_pages.StackPage objects, or (StackPage, sha256-hex) pairs
as sync-stack-rules.py builds them. A bare StackPage's sha256 is read from its
file. check() returns:
  {"codex_home", "copies_dir", "agents_file",
   "copies":  [{"slug", "path", "state"}],   state: in-sync | missing | stale
   "orphans": [{"slug", "path"}],            copies whose page is gone
   "block":   [{"path", "state"}],           AGENTS files needing a change;
                                             state: missing | stale | misplaced | orphan
   "findings": [{"code", "slug", "path", "state"}],
   "in_sync": bool}
with codes `stack-codex-copy-stale` (a missing, stale or orphan copy; slug set)
and `stack-codex-block-stale` (slug None). apply() returns
  {"codex_home", "agents_file",
   "copies": {"wrote", "updated", "removed", "unchanged"},
   "block":  [{"path", "action"}]}           action: wrote | updated | removed | deleted

Stdlib only.
"""

import hashlib
import importlib.util
import os
import stat
import sys
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

sys.dont_write_bytecode = True

COPIES_DIRNAME = "vault-stacks"
AGENTS = "AGENTS.md"
AGENTS_OVERRIDE = "AGENTS.override.md"
START = "<!-- vault-context:stacks:start -->"
END = "<!-- vault-context:stacks:end -->"
_START_B = START.encode()
_END_B = END.encode()
_MARK_TEXT = b"vault-context:stacks:"
HEADING = "## Stack rules"
INSTRUCTION = ("Before you read or edit a file that matches a pattern below, "
               "read the page next to it and follow it.")

_SYNC_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "sync-stack-rules.py")
_MARKER_RE = None


class CodexTargetError(Exception):
    """A refusal: `problems` lists (path, reason); nothing was written."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(f"{p}: {r}" for p, r in self.problems))


def marker_re():
    """sync-stack-rules.py's MARKER_RE: one marker definition for every host.

    Loaded on first use, not at import, so sync-stack-rules.py can import this
    module at its top.
    """
    global _MARKER_RE
    if _MARKER_RE is None:
        main = sys.modules.get("__main__")
        main_file = getattr(main, "__file__", None)
        if (main_file and getattr(main, "MARKER_RE", None) is not None
                and os.path.realpath(main_file) == os.path.realpath(_SYNC_SCRIPT)):
            _MARKER_RE = main.MARKER_RE
        else:
            spec = importlib.util.spec_from_file_location("_vault_context_sync_stack_rules",
                                                          _SYNC_SCRIPT)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _MARKER_RE = mod.MARKER_RE
    return _MARKER_RE


def resolve_codex_home(arg=None):
    """The Codex home: arg (--codex-home), else $CODEX_HOME, else ~/.codex."""
    if arg:
        return os.path.abspath(os.path.expanduser(arg))
    env = os.environ.get("CODEX_HOME")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(os.path.expanduser("~"), ".codex")


# --- what the files hold -------------------------------------------------------

def copy_path(codex_home, slug):
    return os.path.join(codex_home, COPIES_DIRNAME, f"{slug}.md")


def copy_text(page, page_sha):
    """The exact bytes a page's Codex copy holds."""
    marker = f"<!-- vault-context:stack-rule source={page.stack} sha256={page_sha} -->"
    if not marker_re().fullmatch(marker):
        raise CodexTargetError([(page.path, f"marker {marker!r} does not match MARKER_RE")])
    return f"{marker}\n{page.body}".encode("utf-8")


def block_text(codex_home, pages):
    """The block's bytes, start marker through end marker, no final newline."""
    lines = [START, HEADING, "", INSTRUCTION, ""]
    for page in sorted(pages, key=lambda p: p.stack):
        pats = ", ".join(f"`{p}`" for p in page.paths)
        lines.append(f"- {pats} - {copy_path(codex_home, page.stack)}")
    lines.append(END)
    return "\n".join(lines).encode("utf-8")


def read_copy_marker(path):
    """(slug, sha) from line 1 of a generated copy, or None when not ours."""
    try:
        st = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    try:
        with open(path, "rb") as f:
            first = f.readline(4096).decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not first.endswith("\n"):
        return None
    m = marker_re().fullmatch(first[:-1])
    return (m.group(1), m.group(2)) if m else None


# --- the AGENTS file -----------------------------------------------------------

def _read_agents(path, problems):
    """The file's bytes, None when absent; a symlink or non-file is a problem."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(st.st_mode):
        problems.append((path, "is a symlink; replacing it would cut the link, so it is not edited"))
        return None
    if not stat.S_ISREG(st.st_mode):
        problems.append((path, "is not a regular file"))
        return None
    with open(path, "rb") as f:
        return f.read()


def find_block(path, data):
    """(start, end) byte span of the one block, end past its newline; None if
    there is no block. Raises CodexTargetError on any other marker shape."""
    starts, ends, bad = [], [], []
    pos = 0
    for n, line in enumerate(data.split(b"\n"), 1):
        if _MARK_TEXT in line:
            if line == _START_B:
                starts.append((n, pos))
            elif line == _END_B:
                ends.append((n, pos + len(line)))
            else:
                bad.append(n)
        pos += len(line) + 1
    if bad:
        raise CodexTargetError([(path, f"line {bad[0]} holds a vault-context:stacks marker "
                                       "with other text on the line; not edited")])
    if not starts and not ends:
        return None
    if len(starts) > 1 or len(ends) > 1:
        raise CodexTargetError([(path, f"holds {max(len(starts), len(ends))} vault-context stack "
                                       "blocks (start markers on lines "
                                       f"{', '.join(str(s[0]) for s in starts) or 'none'}); "
                                       "expected at most one; not edited")])
    if not ends:
        raise CodexTargetError([(path, f"start marker on line {starts[0][0]} has no end marker; "
                                       "not edited")])
    if not starts:
        raise CodexTargetError([(path, f"end marker on line {ends[0][0]} has no start marker; "
                                       "not edited")])
    (sl, s), (el, e) = starts[0], ends[0]
    if el < sl:
        raise CodexTargetError([(path, f"end marker on line {el} comes before the start marker "
                                       f"on line {sl}; not edited")])
    if e < len(data) and data[e:e + 1] == b"\n":
        e += 1
    return s, e


def _replace(data, span, block):
    s, e = span
    nl = b"\n" if data[e - 1:e] == b"\n" else b""
    return data[:s] + block + nl + data[e:]


def _insert(data, block):
    if not data:
        return block + b"\n"
    sep = b"" if data.endswith(b"\n") else b"\n"
    return data + sep + block + b"\n"


def _remove(data, span):
    s, e = span
    return data[:s] + data[e:]


# --- plan / apply / check ------------------------------------------------------

@dataclass
class CodexPlan:
    codex_home: str
    copies_dir: str
    agents_file: str
    copies: List[dict] = field(default_factory=list)   # slug, path, state, want
    orphans: List[dict] = field(default_factory=list)  # slug, path
    agents: List[dict] = field(default_factory=list)   # path, state, before, after (None: delete)


def _normalise(pages, problems):
    out = []
    for item in pages:
        page, sha = item if isinstance(item, tuple) else (item, None)
        if sha is None:
            with open(page.path, "rb") as f:
                sha = hashlib.sha256(f.read()).hexdigest()
        for pat in page.paths:
            if "`" in pat:
                problems.append((page.path, f"paths pattern {pat!r} holds a backtick, which "
                                            "the pointer line cannot quote"))
        out.append((page, sha))
    seen = set()
    for page, _ in out:
        if page.stack in seen:
            problems.append((page.path, f"a second page for stack {page.stack!r}"))
        seen.add(page.stack)
    return out


def plan(codex_home, pages):
    """What a write would change. Reads only; raises CodexTargetError."""
    home = os.path.abspath(os.path.expanduser(codex_home))
    copies_dir = os.path.join(home, COPIES_DIRNAME)
    problems = []
    pages = _normalise(pages, problems)

    # Copies: every *.md in vault-stacks/ must be ours.
    ours = {}
    if os.path.isdir(copies_dir):
        for name in sorted(os.listdir(copies_dir)):
            if not name.endswith(".md"):
                continue
            path = os.path.join(copies_dir, name)
            mk = read_copy_marker(path)
            if mk is None or mk[0] != name[:-3]:
                problems.append((path, "a .md in vault-stacks/ without the vault-context marker "
                                       "naming its own slug; it was not touched"))
            else:
                ours[name[:-3]] = path

    # AGENTS files: parse both, whichever the block lands in.
    base = os.path.join(home, AGENTS)
    over = os.path.join(home, AGENTS_OVERRIDE)
    files = []
    for path in (over, base):
        data = _read_agents(path, problems)
        span = None
        if data is not None:
            try:
                span = find_block(path, data)
            except CodexTargetError as e:
                problems.extend(e.problems)
        files.append((path, data, span))
    if problems:
        raise CodexTargetError(problems)

    over_data = files[0][1]
    target = over if over_data is not None and over_data.strip() else base

    p = CodexPlan(codex_home=home, copies_dir=copies_dir, agents_file=target)
    slugs = set()
    for page, sha in sorted(pages, key=lambda x: x[0].stack):
        slugs.add(page.stack)
        path = copy_path(home, page.stack)
        want = copy_text(page, sha)
        if page.stack not in ours:
            state = "missing"
        else:
            with open(path, "rb") as f:
                state = "in-sync" if f.read() == want else "stale"
        p.copies.append({"slug": page.stack, "path": path, "state": state, "want": want})
    p.orphans = [{"slug": s, "path": ours[s]} for s in sorted(ours) if s not in slugs]

    block = block_text(home, [pg for pg, _ in pages]) if pages else None
    for path, data, span in files:
        here = block is not None and path == target
        after, state = data, None
        if data is None:
            if here:
                after, state = block + b"\n", "missing"
        elif span is not None:
            if here:
                after = _replace(data, span, block)
                state = None if after == data else "stale"
            else:
                after = _remove(data, span)
                state = "misplaced" if block is not None else "orphan"
                if path == base and after == b"":
                    after = None  # created by this tool: nothing but the block was in it
        elif here:
            after, state = _insert(data, block), "missing"
        if state is not None:
            p.agents.append({"path": path, "state": state, "before": data, "after": after})
    return p


def report(p):
    """The JSON-able view of a plan, with lane findings."""
    findings = []
    for c in p.copies:
        if c["state"] != "in-sync":
            findings.append({"code": "stack-codex-copy-stale", "slug": c["slug"],
                             "path": c["path"], "state": c["state"]})
    for o in p.orphans:
        findings.append({"code": "stack-codex-copy-stale", "slug": o["slug"],
                         "path": o["path"], "state": "orphan"})
    for a in p.agents:
        findings.append({"code": "stack-codex-block-stale", "slug": None,
                         "path": a["path"], "state": a["state"]})
    return {
        "codex_home": p.codex_home,
        "copies_dir": p.copies_dir,
        "agents_file": p.agents_file,
        "copies": [{k: c[k] for k in ("slug", "path", "state")} for c in p.copies],
        "orphans": [dict(o) for o in p.orphans],
        "block": [{"path": a["path"], "state": a["state"]} for a in p.agents],
        "findings": findings,
        "in_sync": not findings,
    }


def check(codex_home, pages):
    """Compare only; never writes. Raises CodexTargetError on a refusal."""
    return report(plan(codex_home, pages))


def _write_atomic(path, data):
    """Temp file in the same folder, then os.replace; an existing file's mode is kept."""
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except FileNotFoundError:
        mode = 0o644
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".vault-context-", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def apply(p):
    """Carry out a plan: copies, then the block, then orphan copies go."""
    # An AGENTS file edited since plan() read it is refused, nothing written.
    changed = []
    for a in p.agents:
        cur = _read_agents(a["path"], changed)
        if cur != a["before"]:
            changed.append((a["path"], "changed since it was read; nothing written, run again"))
    if changed:
        raise CodexTargetError(changed)

    counts = {"wrote": 0, "updated": 0, "removed": 0, "unchanged": 0}
    pending = [c for c in p.copies if c["state"] != "in-sync"]
    if pending:
        os.makedirs(p.copies_dir, exist_ok=True)
    for c in p.copies:
        if c["state"] == "in-sync":
            counts["unchanged"] += 1
            continue
        _write_atomic(c["path"], c["want"])
        counts["wrote" if c["state"] == "missing" else "updated"] += 1

    actions = []
    for a in p.agents:
        if a["after"] is None:
            os.unlink(a["path"])
            action = "deleted"
        else:
            os.makedirs(os.path.dirname(a["path"]), exist_ok=True)
            _write_atomic(a["path"], a["after"])
            action = {"missing": "wrote", "stale": "updated"}.get(a["state"], "removed")
        actions.append({"path": a["path"], "action": action})

    for o in p.orphans:
        # Re-check the marker right before deleting.
        mk = read_copy_marker(o["path"])
        if mk and mk[0] == o["slug"]:
            os.unlink(o["path"])
            counts["removed"] += 1

    return {"codex_home": p.codex_home, "agents_file": p.agents_file,
            "copies": counts, "block": actions}
