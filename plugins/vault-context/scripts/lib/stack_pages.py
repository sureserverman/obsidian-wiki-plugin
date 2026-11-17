#!/usr/bin/env python3
"""stack_pages.py — read a vault stack page and match its `paths:` globs.

A stack page lives at `<vault>/Portfolio/stacks/<slug>.md`. Its frontmatter
holds these keys and no others:

  stack    required  the slug; `[a-z0-9-]+`, equal to the file stem
  paths    required  non-empty list of globs (`**`, `*`, `?`, `{a,b}`)
  sources  required  non-empty list of absolute paths the facts were read from
  related  optional  list of wiki page titles
  checked  required  YYYY-MM-DD, when the facts were last read against sources

The body after the frontmatter is at most 8,192 bytes. A larger page is
refused, never truncated.

Globs follow Claude Code's rule `paths:` semantics, relative to the project
root: a pattern with no slash matches the basename at any depth (`*.md`); a
leading `/` anchors to the top level (`/*.md`); any other slash anchors the
pattern at the root (`src/components/*.tsx`); `**` as a whole segment spans
zero or more folders; `{a,b}` expands. Anything outside that subset — `[`,
a backslash escape, `**` inside a segment, a trailing slash, unbalanced or
comma-less braces — is refused as unsupported rather than emulated.

The frontmatter reader takes `key: value`, `key: [a, b]` and a block list of
quoted or bare strings, and refuses every other shape (W DEC-002). Bare
scalars that real YAML would read differently (an alias `*…`, a flow `{…}`,
a comment) are refused with "quote it", so what this module accepts parses the
same way in Obsidian.

Public API:
  load_page(path) -> StackPage        raises StackPageError
  glob_match(pattern, relpath) -> bool raises ValueError on an unsupported pattern
  applies(page, files) -> bool
  project_files(root) -> list[str]

Stdlib only.
"""

import datetime
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

MAX_BODY_BYTES = 8192
MAX_EXPANSIONS = 256

SLUG_RE = re.compile(r"[a-z0-9-]+")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
KEY_LINE_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]+(.*))?")
ITEM_LINE_RE = re.compile(r"[ \t]*-(?:[ \t]+(.*))?")

REQUIRED_KEYS = ("stack", "paths", "sources", "checked")
SCALAR_KEYS = ("stack", "checked")
LIST_KEYS = ("paths", "sources", "related")
ALLOWED_KEYS = frozenset(SCALAR_KEYS + LIST_KEYS)

# A bare (unquoted) scalar starting with one of these means something else
# to YAML: alias, anchor, tag, block scalar, directive, reserved, flow
# collection, comment.
YAML_INDICATOR_START = frozenset("*&!|>%@`{}[]#")

# Build and dependency trees pruned by the non-git walk.
PRUNED_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "target", "build", "dist",
    ".venv", "venv", "__pycache__", ".gradle", ".tox", ".mypy_cache",
    ".pytest_cache",
})


class StackPageError(Exception):
    """A stack page was refused. `page` is its path, `reason` says why."""

    def __init__(self, page, reason):
        self.page = str(page)
        self.reason = reason
        super().__init__(f"stack page {self.page}: {reason}")


@dataclass(frozen=True)
class StackPage:
    path: str
    stack: str
    paths: Tuple[str, ...]
    sources: Tuple[str, ...]
    related: Tuple[str, ...]
    checked: str
    body: str


# --- frontmatter --------------------------------------------------------------

class _ShapeError(ValueError):
    pass


def _unquote(raw: str, where: str, in_flow: bool = False) -> str:
    s = raw.strip()
    if not s:
        raise _ShapeError(f"{where}: empty value")
    if s[0] in "\"'":
        q = s[0]
        if len(s) < 2 or s[-1] != q:
            raise _ShapeError(f"{where}: unterminated quoted string {s!r}")
        inner = s[1:-1]
        if q in inner:
            raise _ShapeError(f"{where}: quote character inside a quoted string {s!r}")
        if q == '"' and "\\" in inner:
            raise _ShapeError(f"{where}: backslash escapes in double quotes are not supported {s!r}")
        if not inner:
            raise _ShapeError(f"{where}: empty value")
        return inner
    if s[0] in YAML_INDICATOR_START:
        raise _ShapeError(f"{where}: bare value {s!r} starts with YAML indicator {s[0]!r}; quote it")
    if " #" in s or "\t#" in s:
        raise _ShapeError(f"{where}: bare value {s!r} holds a YAML comment; quote it")
    if ": " in s or s.endswith(":"):
        raise _ShapeError(f"{where}: bare value {s!r} reads as a YAML mapping; quote it")
    if in_flow and any(c in s for c in "{}[]"):
        raise _ShapeError(f"{where}: bare value {s!r} in an inline list holds a flow character; quote it")
    return s


def _split_inline(content: str, where: str) -> List[str]:
    """Split the inside of `[ ... ]` on top-level commas, honouring quotes."""
    if not content.strip():
        return []
    items, cur, quote = [], [], None
    for ch in content:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch == ",":
            items.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if quote:
        raise _ShapeError(f"{where}: unterminated quoted string in inline list")
    items.append("".join(cur))
    out = []
    for i, item in enumerate(items, 1):
        if not item.strip():
            raise _ShapeError(f"{where}: empty item {i} in inline list")
        out.append(_unquote(item, f"{where} item {i}", in_flow=True))
    return out


def _parse_frontmatter(lines: List[str]) -> dict:
    data = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        lineno = i + 2  # line 1 is the opening fence
        if not line.strip():
            i += 1
            continue
        m = KEY_LINE_RE.fullmatch(line)
        if not m:
            if ITEM_LINE_RE.fullmatch(line):
                raise _ShapeError(f"frontmatter line {lineno}: list item outside a key's block list")
            raise _ShapeError(f"frontmatter line {lineno}: unparsed line {line!r}")
        key, rest = m.group(1), (m.group(2) or "").strip()
        if key not in ALLOWED_KEYS:
            raise _ShapeError(
                f"unknown frontmatter key {key!r} (allowed: {', '.join(sorted(ALLOWED_KEYS))})")
        if key in data:
            raise _ShapeError(f"duplicate frontmatter key {key!r}")
        where = f"key {key!r}"
        i += 1
        if not rest:
            items = []
            while i < len(lines):
                im = ITEM_LINE_RE.fullmatch(lines[i])
                if not im:
                    break
                items.append(_unquote(im.group(1) or "", f"{where} item {len(items) + 1}"))
                i += 1
            if not items:
                raise _ShapeError(f"{where} has no value")
            data[key] = items
        elif rest.startswith("["):
            if not rest.endswith("]"):
                raise _ShapeError(f"{where}: inline list must close with ']' on the same line")
            data[key] = _split_inline(rest[1:-1], where)
        elif rest[0] in "{|>":
            raise _ShapeError(f"{where}: value shape {rest[0]!r} is not supported "
                              "(use key: value, key: [a, b] or a block list)")
        else:
            data[key] = _unquote(rest, where)
    return data


def _split_page(text: str):
    """Return (frontmatter lines, body) or raise _ShapeError."""
    if "\r" in text:
        raise _ShapeError("line endings must be LF; found a carriage return")
    if not (text.startswith("---\n") or text == "---"):
        raise _ShapeError("no frontmatter: the page must open with a '---' line")
    lines = text.split("\n")
    for idx in range(1, len(lines)):
        if lines[idx] == "---":
            fm = lines[1:idx]
            body = "\n".join(lines[idx + 1:])
            return fm, body
    raise _ShapeError("frontmatter has no closing '---' line")


# --- validation ---------------------------------------------------------------

def _validate(path: str, data: dict, body: str) -> StackPage:
    def refuse(reason):
        raise StackPageError(path, reason)

    for key in REQUIRED_KEYS:
        if key not in data:
            refuse(f"missing required key {key!r}")
    for key in SCALAR_KEYS:
        if isinstance(data[key], list):
            refuse(f"key {key!r} must be a single value, not a list")
    for key in LIST_KEYS:
        if key in data and not isinstance(data[key], list):
            refuse(f"key {key!r} must be a list")

    stack = data["stack"]
    if not SLUG_RE.fullmatch(stack):
        refuse(f"stack slug {stack!r} is not [a-z0-9-]+")
    base = os.path.basename(path)
    if not base.endswith(".md"):
        refuse("a stack page file must end in .md")
    stem = base[:-3]
    if not SLUG_RE.fullmatch(stem):
        refuse(f"file stem {stem!r} is not a valid slug [a-z0-9-]+")
    if stack != stem:
        refuse(f"stack {stack!r} differs from the file stem {stem!r}")

    paths = data["paths"]
    if not paths:
        refuse("key 'paths' is empty; a stack page needs at least one glob")
    for pat in paths:
        reason = pattern_error(pat)
        if reason:
            refuse(f"paths pattern {pat!r}: {reason}")

    sources = data["sources"]
    if not sources:
        refuse("key 'sources' is empty; name the files the facts were read from")
    for src in sources:
        if not os.path.isabs(src):
            refuse(f"source {src!r} is not an absolute path")

    related = data.get("related", [])

    checked = data["checked"]
    if not DATE_RE.fullmatch(checked):
        refuse(f"checked {checked!r} is not a YYYY-MM-DD date")
    try:
        datetime.date.fromisoformat(checked)
    except ValueError:
        refuse(f"checked {checked!r} is not a real calendar date")

    size = len(body.encode("utf-8"))
    if size > MAX_BODY_BYTES:
        refuse(f"body is {size} bytes, over the {MAX_BODY_BYTES}-byte limit "
               "(pages are refused, never truncated)")

    return StackPage(
        path=path,
        stack=stack,
        paths=tuple(paths),
        sources=tuple(sources),
        related=tuple(related),
        checked=checked,
        body=body,
    )


def load_page(path) -> StackPage:
    """Read and validate one stack page. Raises StackPageError on any defect."""
    path = os.fspath(path)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise StackPageError(path, f"cannot read: {e.strerror or e}") from None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise StackPageError(path, f"not valid UTF-8 (byte {e.start})") from None
    try:
        fm_lines, body = _split_page(text)
        data = _parse_frontmatter(fm_lines)
    except _ShapeError as e:
        raise StackPageError(path, str(e)) from None
    return _validate(path, data, body)


# --- globs --------------------------------------------------------------------

def _expand_braces(pattern: str) -> List[str]:
    """Expand {a,b} groups (nested allowed). Raises _ShapeError on bad braces."""
    depth = 0
    start = None
    for i, ch in enumerate(pattern):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth == 0:
                raise _ShapeError("unbalanced '}'")
            depth -= 1
            if depth == 0:
                inner = pattern[start + 1:i]
                alts, cur, d = [], [], 0
                for c in inner:
                    if c == "{":
                        d += 1
                    elif c == "}":
                        d -= 1
                    if c == "," and d == 0:
                        alts.append("".join(cur))
                        cur = []
                    else:
                        cur.append(c)
                alts.append("".join(cur))
                if len(alts) < 2:
                    raise _ShapeError("brace group without a comma is not supported")
                head, tail = pattern[:start], pattern[i + 1:]
                out = []
                for alt in alts:
                    for exp in _expand_braces(head + alt + tail):
                        out.append(exp)
                        if len(out) > MAX_EXPANSIONS:
                            raise _ShapeError(f"expands to more than {MAX_EXPANSIONS} patterns")
                return out
    if depth:
        raise _ShapeError("unbalanced '{'")
    return [pattern]


def _check_alternative(alt: str) -> None:
    body = alt[1:] if alt.startswith("/") else alt
    if not body:
        raise _ShapeError("matches nothing after expansion (empty pattern)")
    if body.endswith("/"):
        raise _ShapeError("trailing '/' (directory patterns) is not supported")
    for seg in body.split("/"):
        if seg == "":
            raise _ShapeError("empty path segment ('//' or a leading '//')")
        if "**" in seg and seg != "**":
            raise _ShapeError("'**' must be a whole path segment")


def pattern_error(pattern) -> Optional[str]:
    """The reason a pattern is unsupported, or None if it is supported."""
    if not isinstance(pattern, str) or not pattern:
        return "empty pattern"
    if "[" in pattern or "]" in pattern:
        return "bracket expressions ('[' / ']') are not supported"
    if "\\" in pattern:
        return "backslash escapes are not supported"
    try:
        for alt in _expand_braces(pattern):
            _check_alternative(alt)
    except _ShapeError as e:
        return str(e)
    return None


def _segment_re(seg: str) -> "re.Pattern[str]":
    out = []
    for ch in seg:
        if ch == "*":
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(ch))
    return re.compile("".join(out))


def _match_segments(pat: List[str], path: List[str]) -> bool:
    memo = {}

    def go(pi, si):
        key = (pi, si)
        if key in memo:
            return memo[key]
        if pi == len(pat):
            res = si == len(path)
        elif pat[pi] == "**":
            res = any(go(pi + 1, k) for k in range(si, len(path) + 1))
        elif si == len(path):
            res = False
        else:
            res = bool(_segment_re(pat[pi]).fullmatch(path[si])) and go(pi + 1, si + 1)
        memo[key] = res
        return res

    return go(0, 0)


def glob_match(pattern: str, relpath: str) -> bool:
    """True if relpath (relative to the project root, '/'-separated) matches.

    Raises ValueError for a pattern outside the supported subset.
    """
    reason = pattern_error(pattern)
    if reason:
        raise ValueError(f"unsupported glob {pattern!r}: {reason}")
    rel = relpath.replace(os.sep, "/") if os.sep != "/" else relpath
    while rel.startswith("./"):
        rel = rel[2:]
    rel = rel.lstrip("/")
    if not rel:
        return False
    parts = rel.split("/")
    for alt in _expand_braces(pattern):
        if alt.startswith("/"):
            segs = alt[1:].split("/")
        elif "/" not in alt:
            segs = ["**", alt]
        else:
            segs = alt.split("/")
        if _match_segments(segs, parts):
            return True
    return False


def applies(page: StackPage, files: Iterable[str]) -> bool:
    """True if any file in `files` matches any of the page's `paths`."""
    files = list(files)
    return any(glob_match(pat, f) for pat in page.paths for f in files)


# --- project files ------------------------------------------------------------

def _git_files(root: str) -> Optional[List[str]]:
    try:
        probe = subprocess.run(
            ["git", "-C", root, "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, check=False)
    except OSError:
        return None
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return None
    res = subprocess.run(["git", "-C", root, "ls-files", "-z"],
                         capture_output=True, check=False)
    if res.returncode != 0:
        return None
    return [p for p in res.stdout.decode("utf-8", "surrogateescape").split("\0") if p]


def _walk_files(root: str) -> List[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in PRUNED_DIRS)
        rel_dir = os.path.relpath(dirpath, root)
        for name in sorted(filenames):
            rel = name if rel_dir == "." else os.path.join(rel_dir, name)
            out.append(rel.replace(os.sep, "/"))
    return out


def project_files(root) -> List[str]:
    """Files under root, relative to it with '/' separators.

    `git ls-files` when root is in a git work tree; otherwise a walk that
    prunes build and dependency trees (PRUNED_DIRS).
    """
    root = os.fspath(root)
    if not os.path.isdir(root):
        raise NotADirectoryError(f"project root is not a directory: {root}")
    files = _git_files(root)
    if files is None:
        files = _walk_files(root)
    return files
