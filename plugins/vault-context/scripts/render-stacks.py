#!/usr/bin/env python3
"""render-stacks.py — render the sidecar's `## Stack rules` block.

Usage:
    render-stacks.py <vault-path> <project-root>

Reads every `<vault>/Portfolio/stacks/*.md` page (lib/stack_pages.py) and keeps
the ones whose `paths:` globs match a file of the project (`git ls-files`, or a
pruned walk outside git). Prints the whole block, markers included, to stdout:

    <!-- vault-context:stacks:start -->
    ## Stack rules

    These load on their own when a matching file is read or edited. Open a page to read it sooner.

    - **<slug>** — `<glob>`, … — `<absolute page path>` — related: [[<title>]], …
    <!-- vault-context:stacks:end -->

Prints nothing when no stack applies or the stacks folder is missing, so the
caller can drop the block entirely. A page that fails to parse gets one warning
on stderr naming the page and the reason, and is skipped: one broken page must
not stop the sidecar being written. Never writes anything.

Exit codes: 0 ok (with or without a block) | 2 usage.

Stdlib only.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from stack_pages import StackPageError, applies, load_page, project_files  # noqa: E402

START = "<!-- vault-context:stacks:start -->"
END = "<!-- vault-context:stacks:end -->"
HEADING = "## Stack rules"
FIRST_LINE = ("These load on their own when a matching file is read or edited. "
              "Open a page to read it sooner.")


def warn(msg: str) -> None:
    print(f"render-stacks: {msg}", file=sys.stderr)


def bullet(page) -> str:
    globs = ", ".join(f"`{g}`" for g in page.paths)
    line = f"- **{page.stack}** — {globs} — `{page.path}`"
    if page.related:
        line += " — related: " + ", ".join(f"[[{t}]]" for t in page.related)
    return line


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: render-stacks.py <vault-path> <project-root>", file=sys.stderr)
        return 2
    vault, root = sys.argv[1], sys.argv[2]
    stacks_dir = os.path.join(os.path.abspath(vault), "Portfolio", "stacks")
    if not os.path.isdir(stacks_dir):
        return 0

    names = sorted(n for n in os.listdir(stacks_dir)
                   if n.endswith(".md") and os.path.isfile(os.path.join(stacks_dir, n)))
    if not names:
        return 0

    try:
        files = project_files(root)
    except OSError as e:
        warn(f"cannot list project files under {root}: {e}; no stack block rendered")
        return 0

    bullets = []
    for name in names:
        path = os.path.join(stacks_dir, name)
        try:
            page = load_page(path)
        except StackPageError as e:
            warn(f"skipped {e.page}: {e.reason}")
            continue
        if applies(page, files):
            bullets.append(bullet(page))

    if not bullets:
        return 0
    print("\n".join([START, HEADING, "", FIRST_LINE, "", *bullets, END]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
