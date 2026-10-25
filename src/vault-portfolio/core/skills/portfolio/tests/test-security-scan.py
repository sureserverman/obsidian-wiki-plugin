#!/usr/bin/env python3
"""Fixture tests for the global-security roll-up lane.

Builds a synthetic vault + registry, runs `security-scan.py | security-rollup.py`
end to end, and asserts the behaviours that make this dashboard trustworthy:

  * an UNRECORDED count is `null` in the scan and `?` in the render — never `0`.
    Collapsing the two would show a never-measured project as clean, which is
    the worst thing a security dashboard can do.
  * a `mode: "feeds"` run is flagged: it re-checked advisories without running a
    code lane, so its counts are carried forward, not re-verified.
  * unknown keys and unknown `mode` values pass through — the producer (an
    external security-audit tool) is maintained elsewhere and will add fields.
  * one broken project never aborts the sweep.
  * with no override set, the scan reads the vault and the registry from the
    plugin's own configuration (`_config.py`): obsidian-wiki's config.json, or
    $OBSIDIAN_VAULT_PATH above it. Unconfigured or unreachable is refused.
  * PORTFOLIO_CONFIG and SECURITY_REGISTRY, the test overrides, outrank that
    configuration and are documented in the scan's --help.

Every run uses a throwaway HOME and a scrubbed environment, so nothing here
reads the machine's real configuration, registry or vault.

No pytest. Plain assertions, non-zero exit on failure.
Run: python3 -I src/vault-portfolio/core/skills/portfolio/tests/test-security-scan.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
SCAN = SCRIPTS / "security-scan.py"
ROLLUP = SCRIPTS / "security-rollup.py"


def build_vault(tmp: Path) -> tuple[Path, Path, Path]:
    vault = tmp / "vault"
    (vault / "Portfolio").mkdir(parents=True)
    projects = []

    def proj(area, name, runs=None, reports=False):
        home = vault / "Portfolio" / area / name
        (home / "security").mkdir(parents=True, exist_ok=True)
        if reports:
            (home / "security" / "reports").mkdir(exist_ok=True)
        if runs is not None:
            (home / "security" / "history.jsonl").write_text(
                "".join(json.dumps(r) + "\n" if isinstance(r, dict) else r + "\n"
                        for r in runs))
        projects.append({"path": f"/srv/{area}/{name}", "name": name,
                         "area": area, "enabled": True})

    # clean, fully-recorded, improving
    proj("web", "clean", [
        {"run_id": "20260701-1200", "mode": "full",
         "counts": {"critical": 3, "high": 4}, "deltas": {"total_open": 7, "accepted": 0}},
        {"run_id": "20260710-1200", "mode": "incremental",
         "counts": {"critical": 0, "high": 0}, "deltas": {"total_open": 0, "accepted": 0}}])
    # at risk, worsening, with acceptances
    proj("web", "risky", [
        {"run_id": "20260701-1200", "mode": "full",
         "counts": {"critical": 1, "high": 1}, "deltas": {"total_open": 2, "accepted": 0}},
        {"run_id": "20260720-1200", "mode": "incremental",
         "counts": {"critical": 5, "high": 2}, "deltas": {"total_open": 9, "accepted": 2}}])
    # newest run is FEED-ONLY: counts carried, code not re-verified
    proj("infra", "feedonly", [
        {"run_id": "20260701-1200", "mode": "full",
         "counts": {"critical": 1, "high": 0}, "deltas": {"total_open": 1}},
        {"run_id": "20260724-1200", "mode": "feeds",
         "counts": {"critical": 1, "high": 0}, "deltas": {"total_open": 1}}])
    # audited but counts NOT recorded — must be `?`, never 0
    proj("infra", "unmeasured", [{"run_id": "20260724-1200", "mode": "incremental"}])
    # malformed lines are skipped and counted, the good record still wins
    proj("infra", "partial", [
        "{not json",
        {"run_id": "20260724-1200", "mode": "full",
         "counts": {"critical": 0, "high": 1}, "deltas": {"total_open": 1}},
        "[]"])
    # unknown mode + unknown keys must pass through untouched
    proj("infra", "future", [
        {"run_id": "20260724-1200", "mode": "quantum", "counts": {"critical": 0, "high": 0},
         "deltas": {"total_open": 0}, "some_future_field": {"x": 1}}])
    # never audited (no history at all), and one with reports but no history
    proj("web", "never", None)
    proj("web", "reportsonly", None, reports=True)

    reg = tmp / "registry.yaml"
    reg.write_text("version: 1\nprojects:\n" + "".join(
        f"  - path: {p['path']}\n    name: {p['name']}\n    area: {p['area']}\n"
        f"    enabled: true\n" for p in projects))
    cfg = tmp / "config.yaml"
    cfg.write_text(f"vault_dir: {vault}\n")
    return cfg, reg, vault


def new_home(tmp: Path, name: str, config: dict | None = None) -> Path:
    """A throwaway HOME; `config` becomes its obsidian-wiki config.json."""
    h = tmp / name
    (h / ".config" / "obsidian-wiki").mkdir(parents=True)
    (h / ".claude").mkdir()
    if config is not None:
        (h / ".config" / "obsidian-wiki" / "config.json").write_text(json.dumps(config))
    return h


def scrubbed(home: Path, **extra) -> dict:
    """Only HOME and PATH, plus what the case sets: no override leaks in from the caller."""
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    env.update({k: str(v) for k, v in extra.items()})
    return env


def scan(env: dict, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(SCAN), *args],
                          capture_output=True, text=True, env=env)


def run_scan(env: dict) -> dict:
    p = scan(env)
    if p.returncode != 0:
        raise AssertionError(f"scan exited {p.returncode}: {p.stderr}")
    return json.loads(p.stdout)


def run_rollup(doc: dict) -> str:
    p = subprocess.run([sys.executable, "-I", str(ROLLUP)], input=json.dumps(doc),
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise AssertionError(f"rollup exited {p.returncode}: {p.stderr}")
    return p.stdout


def main() -> int:
    fails: list[str] = []

    def chk(cond, msg):
        if not cond:
            fails.append(msg)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg, reg, vault = build_vault(tmp)

        # A decoy vault and registry in config.json: the overrides must outrank them.
        decoy = tmp / "decoy-vault"
        (decoy / "Portfolio").mkdir(parents=True)
        decoy_reg = tmp / "decoy-registry.yaml"
        decoy_reg.write_text("version: 1\nprojects: []\n")
        h_over = new_home(tmp, "home-overrides",
                          {"default_vault": str(decoy), "registry": str(decoy_reg)})
        env_over = scrubbed(h_over, PORTFOLIO_CONFIG=cfg, SECURITY_REGISTRY=reg)

        doc = run_scan(env_over)
        by = {p["name"]: p for p in doc["projects"]}

        chk(doc["vault_dir"] == str(vault),
            f"PORTFOLIO_CONFIG must outrank config.json: scanned {doc['vault_dir']}")
        chk(len(doc["projects"]) == 8, f"scanned {len(doc['projects'])} projects, expected 8")
        chk(not doc["couldnt_assess"], f"unexpected couldnt_assess: {doc['couldnt_assess']}")

        # --- newest run wins, counts read from it
        chk(by["clean"]["critical"] == 0 and by["clean"]["high"] == 0,
            f"clean: {by['clean']}")
        chk(by["clean"]["trend"] == "down", f"clean trend {by['clean']['trend']}")
        chk(by["risky"]["critical"] == 5 and by["risky"]["trend"] == "up",
            f"risky: {by['risky']}")
        chk(by["risky"]["accepted"] == 2 and by["risky"]["unsuppressed_open"] == 7,
            f"risky suppression math: {by['risky']}")

        # --- THE rule: unrecorded is null, not zero
        u = by["unmeasured"]
        chk(u["critical"] is None and u["high"] is None,
            f"unmeasured counts must be null, got {u['critical']}/{u['high']}")
        chk(u["total_open"] is None and u["unsuppressed_open"] is None,
            f"unmeasured totals must be null: {u}")
        chk(u["never_audited"] is False, "a run with no counts is still an audit")

        # --- feed-only runs are marked as not code-verified
        f = by["feedonly"]
        chk(f["mode"] == "feeds" and f["code_verified"] is False, f"feedonly: {f}")
        chk(by["clean"]["code_verified"] is True, "incremental must be code-verified")

        # --- malformed lines skipped, counted, good record still used
        pt = by["partial"]
        chk(pt["malformed_lines"] == 2, f"expected 2 malformed lines, got {pt['malformed_lines']}")
        chk(pt["high"] == 1, f"partial should still read its good record: {pt}")

        # --- forward compatibility
        fu = by["future"]
        chk(fu["mode"] == "quantum", f"unknown mode must pass through: {fu['mode']}")
        chk(fu["code_verified"] is True, "only `feeds` means not-code-verified")

        # --- never audited
        chk(by["never"]["never_audited"] is True, "never: expected never_audited")
        chk(by["reportsonly"]["never_audited"] is True
            and "reports" in (by["reportsonly"]["note"] or ""),
            f"reportsonly should note its reports dir: {by['reportsonly']}")

        # --- render
        md = run_rollup(doc)
        chk("| `web/risky` |" in md, "risky missing from table")
        chk(md.index("`web/risky`") < md.index("`web/clean`"),
            "worst-first ordering: risky must precede clean")
        chk("| ? | ? |" in md, "unrecorded counts must render as ?, not 0")
        chk("feeds ⚠" in md, "a feed-only run must be flagged in the table")
        chk("not re-verified" in md, "the ⚠ legend must explain feed-only runs")
        chk("`Open − Accepted`" in md, "render must state the suppression math")
        chk("## Never audited" in md and "`web/never`" in md, "never-audited section missing")
        chk("2 malformed line(s)" in md, "history problems not surfaced")
        chk("not** the same as clean" in md, "must warn that ? is not clean")

        # --- rollup input handling
        bad = subprocess.run([sys.executable, "-I", str(ROLLUP)], input="not json",
                             capture_output=True, text=True)
        chk(bad.returncode != 0 and "not valid JSON" in bad.stderr,
            f"malformed stdin should fail loudly: rc={bad.returncode} {bad.stderr!r}")

        # --- an empty portfolio renders honestly rather than looking clean
        empty = run_rollup({"generated": "x", "projects": [], "couldnt_assess": []})
        chk("nothing has been audited" in empty, "empty sweep must say so explicitly")

        # --- the re-pathed configuration: no override, config.json names both
        h_cfg = new_home(tmp, "home-config", {"default_vault": str(vault), "registry": str(reg)})
        p = scan(scrubbed(h_cfg))
        try:
            d = json.loads(p.stdout) if p.returncode == 0 else None
        except ValueError:
            d = None
        chk(d is not None and d["vault_dir"] == str(vault) and len(d["projects"]) == 8,
            f"with no override the scan must read config.json's vault and registry: "
            f"rc={p.returncode} vault={d and d['vault_dir']} stderr={p.stderr.strip()[:300]!r}")

        # --- $OBSIDIAN_VAULT_PATH outranks config.json's default_vault
        h_env = new_home(tmp, "home-envvar", {"default_vault": str(decoy), "registry": str(reg)})
        p = scan(scrubbed(h_env, OBSIDIAN_VAULT_PATH=vault))
        try:
            d = json.loads(p.stdout) if p.returncode == 0 else None
        except ValueError:
            d = None
        chk(d is not None and d["vault_dir"] == str(vault),
            f"OBSIDIAN_VAULT_PATH must outrank config.json: rc={p.returncode} "
            f"vault={d and d['vault_dir']} stderr={p.stderr.strip()[:300]!r}")

        # --- unconfigured: refused, never a guessed vault
        h_none = new_home(tmp, "home-unconfigured", {"registry": str(reg)})
        p = scan(scrubbed(h_none))
        chk(p.returncode != 0 and "not configured" in p.stderr and not p.stdout.strip(),
            f"an unconfigured vault must be refused: rc={p.returncode} "
            f"stdout={p.stdout[:120]!r} stderr={p.stderr.strip()[:300]!r}")

        # --- unreachable: a vault with no Portfolio/ is refused by the one guard
        hollow = tmp / "hollow-vault"
        hollow.mkdir()
        h_hollow = new_home(tmp, "home-hollow", {"default_vault": str(hollow), "registry": str(reg)})
        p = scan(scrubbed(h_hollow))
        chk(p.returncode != 0 and "vault unreachable" in p.stderr and not p.stdout.strip(),
            f"a vault with no Portfolio/ must be refused as unreachable: rc={p.returncode} "
            f"stdout={p.stdout[:120]!r} stderr={p.stderr.strip()[:300]!r}")

        # --- the test overrides are documented where an operator looks
        p = scan(scrubbed(h_none), "--help")
        chk(p.returncode == 0 and "PORTFOLIO_CONFIG" in p.stdout
            and "SECURITY_REGISTRY" in p.stdout,
            f"--help must document PORTFOLIO_CONFIG and SECURITY_REGISTRY: "
            f"rc={p.returncode} {p.stdout[:300]!r} {p.stderr.strip()[:200]!r}")
        p = subprocess.run([sys.executable, "-I", str(ROLLUP), "--help"],
                           capture_output=True, text=True)
        chk(p.returncode == 0 and "stdin" in p.stdout,
            f"rollup --help must say it reads the scan's JSON on stdin: rc={p.returncode} "
            f"{p.stdout[:300]!r}")

        # --- a broken project does not abort the sweep
        broken = vault / "Portfolio" / "web" / "clean" / "security" / "history.jsonl"
        broken.unlink()
        broken.mkdir()          # a directory where a file belongs
        doc2 = run_scan(env_over)
        chk(len(doc2["projects"]) + len(doc2["couldnt_assess"]) == 8,
            f"sweep lost a project: {len(doc2['projects'])}+{len(doc2['couldnt_assess'])}")
        chk(any(c["name"] == "clean" for c in doc2["couldnt_assess"]),
            f"broken project should land in couldnt_assess: {doc2['couldnt_assess']}")
        md2 = run_rollup(doc2)
        chk("## Could not assess" in md2, "couldnt_assess must be rendered")

    if fails:
        print("FAILURES:", file=sys.stderr)
        for f in fails:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("OK — security scan + rollup: counts, feed-only flagging, malformed "
          "tolerance, forward compat, ordering, configuration and degradation all verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
