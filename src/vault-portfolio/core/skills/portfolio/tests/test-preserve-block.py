#!/usr/bin/env python3
"""The hand-curated PRESERVE block of global-backlog.md survives a rebuild.

The roll-up is regenerated on every `rebuild --write`, except for the
`## Cross-project items` section between the PRESERVE sentinels, which is
hand-curated and must come back byte-for-byte. The vault has no version control
behind it, so a rebuild that drops the block loses it for good.

This is a DATA-LOSS regression test, so it asserts the curated bytes come back,
not merely that the sentinels are present — a check for the sentinels alone
passes against the very bug it is meant to catch. An ambiguous file (duplicate,
reversed or quoted sentinels, undecodable bytes) is refused and left alone,
through main() as well as in the helper.

Throwaway HOME and temp vaults only. Stdlib + PyYAML, no pytest. Run:
  python3 -I src/vault-portfolio/core/skills/portfolio/tests/test-preserve-block.py
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "portfolio-rebuild.py"

for _k in list(os.environ):
    if _k.startswith(("OBSIDIAN_", "BUSINESS_", "VAULT_CONTEXT_")):
        os.environ.pop(_k)
os.environ["HOME"] = tempfile.mkdtemp(prefix="preserve-home-")

spec = importlib.util.spec_from_file_location("portfolio_rebuild", SCRIPT)
pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr)

FAILURES = []


def check(ok, msg):
    print(f"  {'ok' if ok else 'FAIL'}: {msg}")
    if not ok:
        FAILURES.append(msg)


CURATED = ("- [[example-app]] ↔ [[example-cli]] — the cli reads the app's export\n"
           "  format, so a format change breaks it silently.\n"
           "- Revisit the 8-in-flight cap once the vault moves to faster storage.")


def rollup(body):
    return ("# Global Backlog\n\n**Last rebuilt:** 2026-01-01\n\n---\n\n"
            "## Per-project backlogs\n\n---\n\n## Cross-project items\n\n"
            f"{pr.PRESERVE_BEGIN}\n\n{body}\n\n{pr.PRESERVE_END}\n")


def cases():
    with tempfile.TemporaryDirectory() as root:
        vd = Path(root)
        (vd / "Portfolio").mkdir()
        path = vd / "Portfolio" / "global-backlog.md"

        # The load-bearing case: curated content already on disk.
        path.write_text(rollup(CURATED))
        out = pr.render_global_backlog(vd, [], pr.preserved_region(path))
        check(CURATED in out,
              "curated PRESERVE content survives a re-render byte-for-byte")
        check(out.count(pr.PRESERVE_BEGIN) == 1 and out.count(pr.PRESERVE_END) == 1,
              "exactly one sentinel pair is emitted, not a nested duplicate")

        # Idempotence: rendering the output again must not drift or double it.
        path.write_text(out)
        again = pr.render_global_backlog(vd, [], pr.preserved_region(path))
        check(again == out, "a second rebuild over its own output is byte-identical")
        check(again.count(CURATED.splitlines()[0]) == 1,
              "the curated body is not duplicated on the second pass")

        # An empty curated block stays empty and stays well-formed.
        path.write_text(rollup(""))
        empty = pr.render_global_backlog(vd, [], pr.preserved_region(path))
        check(pr.PRESERVE_BEGIN in empty and pr.PRESERVE_END in empty,
              "an empty curated block round-trips with its sentinels intact")

        # No file yet — a first run must not warn or invent content.
        missing = vd / "Portfolio" / "does-not-exist.md"
        err = io.StringIO()
        with redirect_stderr(err):
            check(pr.preserved_region(missing) == "",
                  "a first run with no existing roll-up yields an empty region")
        check(err.getvalue() == "",
              "...and does not warn — absent is not the same as damaged")

        # Sentinels missing from a NON-EMPTY file: insert an empty block AND warn.
        # Silence here is how curated items disappear without anyone being told.
        path.write_text("# Global Backlog\n\nsomeone reformatted this by hand\n")
        err = io.StringIO()
        with redirect_stderr(err):
            region = pr.preserved_region(path)
        check(region == "", "a file with no sentinels yields an empty region")
        check("PRESERVE" in err.getvalue(),
              "...and WARNS, rather than silently dropping items")

        # The recovery path the warning above prescribes: an operator pastes the
        # recovered section back — sentinels included — below the generated empty
        # pair. Taking the first pair would return the EMPTY one and destroy the
        # recovery, on the run where the content was already lost once.
        path.write_text(rollup("") + "\n## Recovered by hand\n\n"
                        + f"{pr.PRESERVE_BEGIN}\n\n{CURATED}\n\n{pr.PRESERVE_END}\n")
        err = io.StringIO()
        with redirect_stderr(err):
            region = pr.preserved_region(path)
        check(region is None,
              "duplicate sentinel pairs REFUSE the rewrite (None), never return ''")
        check("2 BEGIN" in err.getvalue() and "REFUSING" in err.getvalue(),
              "...and the warning names the counts and says nothing was written")

        # A curated item quoting the end sentinel — exactly the kind of note that
        # documents this mechanism — must not truncate the region there.
        path.write_text(rollup(f"- item one quotes the sentinel {pr.PRESERVE_END} here\n"
                               "- item two"))
        err = io.StringIO()
        with redirect_stderr(err):
            region = pr.preserved_region(path)
        check(region is None,
              "an end sentinel inside the curated body REFUSES rather than truncating")

        # Sentinels present but reversed.
        path.write_text("# Global Backlog\n\n## Cross-project items\n\n"
                        f"{pr.PRESERVE_END}\n\n{CURATED}\n\n{pr.PRESERVE_BEGIN}\n")
        err = io.StringIO()
        with redirect_stderr(err):
            region = pr.preserved_region(path)
        check(region is None, "out-of-order sentinels REFUSE the rewrite")

        # A non-UTF-8 byte must neither crash the run NOR be silently dropped. On
        # the one path whose contract is byte-for-byte, "drop what I cannot read"
        # returns a curated body with characters gone and writes it back: that is
        # the corruption, not a fix.
        path.write_bytes(rollup(CURATED).encode() + b"\xff\xfe stray latin-1\n")
        err = io.StringIO()
        with redirect_stderr(err):
            region = pr.preserved_region(path)
        check(region is None,
              "an undecodable file REFUSES the rewrite rather than dropping bytes")
        check("UTF-8" in err.getvalue(),
              "...and names the decode failure, rather than failing silently")


def call_site_cases():
    """The data loss had two halves, and the guard covers both.

    A renderer that ignores the existing content, and a main() that does not pass
    it. A test that drives the renderer directly stays green when only the call
    site regresses. So `preserved` is a REQUIRED positional — dropping it at the
    call site is a TypeError, not a silent revert — and this asserts the signature,
    because the signature is what makes the call site checkable.
    """
    import inspect
    sig = inspect.signature(pr.render_global_backlog)
    p = sig.parameters.get("preserved")
    check(p is not None and p.default is inspect.Parameter.empty,
          "render_global_backlog takes `preserved` with NO default, so dropping it "
          "at the call site fails loudly instead of silently restoring the bug")
    try:
        pr.render_global_backlog(Path("/nonexistent"), [])
        check(False, "calling without `preserved` raises TypeError")
    except TypeError:
        check(True, "calling without `preserved` raises TypeError")


def main_level_cases():
    """The REFUSAL holds through `main()`, not only in `preserved_region`.

    The same "green helper, regressed call site" gap one level up: a call site
    written as `render_global_backlog(vd, projects, preserved or "")` keeps the
    signature check green while rewriting an ambiguous file with an EMPTY block —
    and the script would still print "REFUSING to rewrite it". `preserved or ""`
    is what someone writes when a None surprises them. So this drives the real
    entry point against a temp vault and asserts the bytes on disk, the one thing
    a warning cannot satisfy.
    """
    import yaml
    with tempfile.TemporaryDirectory() as root:
        rootp = Path(root)
        vault, repo = rootp / "vault", rootp / "repo"
        (vault / "Portfolio" / "area" / "proj").mkdir(parents=True)
        (repo / ".claude").mkdir(parents=True)
        gb = vault / "Portfolio" / "global-backlog.md"

        # Ambiguous by duplicate pairs — the recovery-path shape.
        original = (rollup("") + "\n## Recovered by hand\n\n"
                    + f"{pr.PRESERVE_BEGIN}\n\n{CURATED}\n\n{pr.PRESERVE_END}\n")
        gb.write_text(original)

        reg = rootp / "registry.yaml"
        reg.write_text(yaml.safe_dump({"projects": [
            {"path": str(repo), "name": "proj", "area": "area", "enabled": True}]}))
        home = rootp / "home"
        cfg = home / ".config" / "obsidian-wiki" / "config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"default_vault": str(vault), "registry": str(reg)}))

        old_home, old_argv = os.environ["HOME"], sys.argv
        os.environ["HOME"] = str(home)
        sys.argv = ["portfolio-rebuild.py", "--write"]
        try:
            with redirect_stderr(io.StringIO()) as err, redirect_stdout(io.StringIO()) as out:
                try:
                    pr.main()
                except SystemExit:
                    pass
            stderr, stdout = err.getvalue(), out.getvalue()
        finally:
            os.environ["HOME"], sys.argv = old_home, old_argv

        check(gb.read_text() == original,
              "main() --write leaves an ambiguous global-backlog.md BYTE-IDENTICAL")
        check("REFUSING" in stderr, "...and says so on stderr")
        check("SKIPPED" in stdout,
              "...and the status line reports a refusal, not a bare False")
        # The refusal must be SCOPED. Halting the whole rebuild would be a
        # different bug with the same symptom.
        check((vault / "Portfolio" / "global-maturity.md").exists(),
              "...while the other roll-ups are still written — the refusal is scoped")


def legacy_marker_cases():
    """A sidecar written under an earlier BEGIN wording is replaced in place.

    The managed block's BEGIN line names the skill that owns it, and that name has
    changed once. Sidecars already committed in repos still carry the old line, so
    a writer that matches only the current string finds no block and appends a
    second one. Both sidecar writers (rebuild's, which the resolver also calls, and
    migrate's) must take any PORTFOLIO-STATUS-BEGIN line as the start of the block.
    """
    mspec = importlib.util.spec_from_file_location(
        "portfolio_migrate", HERE.parent / "scripts" / "portfolio-migrate.py")
    pm = importlib.util.module_from_spec(mspec)
    mspec.loader.exec_module(pm)
    # Spelled apart so this file carries no literal retired id.
    old_begin = ("<!-- PORTFOLIO-STATUS-BEGIN — managed by /planning" + ":portfolio"
                 " rebuild; do not hand-edit -->")
    check("/vault-portfolio:portfolio" in pr.BEGIN and pr.BEGIN != old_begin,
          "the BEGIN marker names /vault-portfolio:portfolio")
    before = "# Vault context for example-app\n\nhand-written notes above\n\n"
    after = "\n\nhand-written notes below\n"
    stale = (f"{before}{old_begin}\n## Portfolio status\n\n- **Home:** `/old/home`\n"
             f"{pr.END}{after}")
    writers = [
        ("rebuild", lambda repo, home, vd: pr.write_sidecar(str(repo), home, vd, True)),
        ("migrate", lambda repo, home, vd: pm.write_sidecar_home(repo, home)),
    ]
    for label, write in writers:
        with tempfile.TemporaryDirectory() as root:
            rootp = Path(root)
            repo, vd = rootp / "example-app", rootp / "vault"
            home = vd / "Portfolio" / "apps" / "example-app"
            home.mkdir(parents=True)
            (repo / ".claude").mkdir(parents=True)
            sc = repo / ".claude" / "vault-context.md"
            sc.write_text(stale)
            write(repo, home, vd)
            got = sc.read_text()
            check(got.count("PORTFOLIO-STATUS-BEGIN") == 1
                  and got.count(pr.END) == 1,
                  f"{label}: an old-marker block is replaced, not duplicated")
            check(pr.BEGIN in got and old_begin not in got,
                  f"{label}: the replaced block carries the new marker")
            check(got.startswith(before) and got.endswith(after)
                  and str(home) in got and "/old/home" not in got,
                  f"{label}: content outside the block is kept, the block is refreshed")


def sidecar_ambiguity_cases():
    """A sidecar whose markers do not frame exactly one block is left as it is.

    Everything outside the managed block is the user's. A BEGIN line with no END
    after it, or a BEGIN without its closing `-->` on the same line, does not mark
    where a block ends: a writer that appended a fresh block after it would, on the
    next run, read from the stray BEGIN to the fresh END and delete the user text
    between them. So both writers leave such a file byte-identical, run after run.
    """
    mspec = importlib.util.spec_from_file_location(
        "portfolio_migrate_ambiguity", HERE.parent / "scripts" / "portfolio-migrate.py")
    pm = importlib.util.module_from_spec(mspec)
    mspec.loader.exec_module(pm)
    writers = [
        ("rebuild", lambda repo, home, vd: pr.write_sidecar(str(repo), home, vd, True)),
        ("migrate", lambda repo, home, vd: pm.write_sidecar_home(repo, home)),
    ]
    user = "my own notes, which no writer may delete\n"
    stray = pr.BEGIN + "\n"
    ambiguous = {
        "a stray BEGIN with no END": f"# ctx\n\n{stray}{user}",
        "a BEGIN whose `-->` is on another line":
            f"# ctx\n\n<!-- PORTFOLIO-STATUS-BEGIN managed\n-->\n{user}\n{pr.END}\n",
        "a stray BEGIN before a whole block":
            f"# ctx\n\n{stray}{user}\n{pr.BEGIN}\n## Portfolio status\n{pr.END}\n",
        "END before BEGIN": f"# ctx\n\n{pr.END}\n{user}{stray}",
    }
    for label, text in ambiguous.items():
        check(pr.splice_sidecar(text, "NEW BLOCK") == text,
              f"splice_sidecar leaves {label} unchanged")
        for wlabel, write in writers:
            with tempfile.TemporaryDirectory() as root:
                rootp = Path(root)
                repo, vd = rootp / "example-app", rootp / "vault"
                home = vd / "Portfolio" / "apps" / "example-app"
                home.mkdir(parents=True)
                (repo / ".claude").mkdir(parents=True)
                sc = repo / ".claude" / "vault-context.md"
                sc.write_text(text)
                write(repo, home, vd)
                write(repo, home, vd)
                check(sc.read_text() == text,
                      f"{wlabel}, {label}: two runs leave the file byte-identical, the "
                      f"user text intact")
    # The controls: an unambiguous file is still spliced.
    block = f"{pr.BEGIN}\n## Portfolio status\n{pr.END}"
    check(pr.splice_sidecar("# ctx\n", "NEW") == "# ctx\n\nNEW\n",
          "no markers at all: the block is appended")
    got = pr.splice_sidecar(f"# ctx\n\n{block}\n{user}", "NEW")
    check(got == f"# ctx\n\nNEW\n{user}", "one whole block is replaced in place")
    once = pr.splice_sidecar(f"# ctx\n{pr.END}\n{user}", block)
    twice = pr.splice_sidecar(once, "NEW")
    check(user in once and twice == f"# ctx\n{pr.END}\n{user}\nNEW\n",
          "a stray END alone: the block is appended once, then replaced, and the user "
          "text stays")


if __name__ == "__main__":
    print("PRESERVE block survival:")
    cases()
    print("call-site contract:")
    call_site_cases()
    print("main()-level refusal:")
    main_level_cases()
    print("sidecar block under an earlier marker:")
    legacy_marker_cases()
    print("sidecar markers that frame no single block:")
    sidecar_ambiguity_cases()
    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed")
        sys.exit(1)
    print("OK")
