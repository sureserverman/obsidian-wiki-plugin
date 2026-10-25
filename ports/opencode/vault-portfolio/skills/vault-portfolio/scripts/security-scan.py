#!/usr/bin/env python3
"""Sweep every registry project's security state into one JSON document.

Reads `<vault>/Portfolio/<area>/<name>/security/history.jsonl` — the run history
an external security-audit tool appends — for each enabled project and emits a
normalised summary on stdout for `security-rollup.py` to render.

The input contract belongs to that tool. Two rules from it drive almost every
decision here:

  * **Optional fields normalise to `null`, never `0`.** "We did not record this"
    and "this was zero" are different facts. A dashboard that renders a missing
    CRITICAL count as `0` reports a clean project that was never measured — the
    single most dangerous thing a security roll-up can do.
  * **`mode: "feeds"` means no code lane ran.** Its unchanged counts are NOT
    evidence the code was re-verified, so a feed-only check must never be
    presented as an audit.

Unknown keys and unknown enum values are passed through, never rejected: this
file is maintained apart from its producer and must not break when the producer
adds a field.

An entry that sets `records: repo` has no vault home, so it lands in
`couldnt_assess` with that reason and nothing under its old vault path is read.
A broken project never aborts the sweep — it lands in `couldnt_assess` with a
reason, because a roll-up that dies on one bad file tells you nothing about the
other thirty. A missing or unusable registry is different: it is refused with a
non-zero exit and no JSON, because a registry that is not there is not a
portfolio with no projects.

Pure stdlib + pyyaml. No network. Writes nothing.
"""
import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

SUPPORTED_SCHEMA = 1
TREND_WINDOW = 5          # runs considered when computing a direction
CONFIG_ENV = "PORTFOLIO_CONFIG"
REGISTRY_ENV = "SECURITY_REGISTRY"

# _config.py is loaded by path: under `python3 -I` the script's own directory is
# not on sys.path, so a bare `import _config` would fail.
_cspec = importlib.util.spec_from_file_location(
    "_vault_portfolio_config", Path(__file__).resolve().parent / "_config.py")
_config = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(_config)

HELP_EPILOG = f"""\
where the vault and the registry come from:
  vault     ${CONFIG_ENV}'s vault_dir when that override is set, else the plugin's
            configuration: $OBSIDIAN_VAULT_PATH, then obsidian-wiki's config.json
            default_vault, then the legacy portfolio-config.yaml vault_dir.
            Unset is refused; so is a vault that is unreachable (missing,
            relative, or without Portfolio/).
  registry  ${REGISTRY_ENV} when set, else the overriding config's `registry:` key,
            else the plugin's registry location. A registry that is missing, is
            not valid YAML, has no `projects:` list or holds a malformed entry is
            refused, never read as empty or as a smaller portfolio.

test overrides (environment):
  {CONFIG_ENV}   a YAML file holding vault_dir (and optionally registry); it
                     outranks the plugin's configuration. A missing file is refused.
  {REGISTRY_ENV}  the registry file to read; it outranks every other source.

Prints one JSON document on stdout; exits non-zero with the reason on stderr.
"""


def _rebuild():
    """portfolio-rebuild.py as a module: the one reachability guard and the one
    registry validator live there.

    Loaded LAZILY: this module is loaded by path by siblings (for its helpers,
    not its resolver), and a module-scope load would make every such importer pay
    for a resolver it never calls. Neither check is restated here — a second copy
    of its conditions is a second place for them to drift.
    """
    return _config.load_module("skills/vault-portfolio/scripts/portfolio-rebuild.py")


def _require_vault(path, source):
    """Delegate to portfolio-rebuild.py's one reachability guard."""
    return _rebuild().require_vault(path, source)


def _read_yaml(path, what):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        sys.exit(f"portfolio not configured: {what} {path} could not be read: {e}")


def config_for():
    """($PORTFOLIO_CONFIG as a Path, its parsed mapping), or (None, None) when unset."""
    alias = (os.environ.get(CONFIG_ENV) or "").strip()
    if not alias:
        return None, None
    cfg_p = Path(alias).expanduser()
    if not cfg_p.is_file():
        sys.exit(f"portfolio not configured: {cfg_p} ({CONFIG_ENV}) not found")
    cfg = _read_yaml(cfg_p, "config")
    if not isinstance(cfg, dict):
        sys.exit(f"portfolio not configured: {cfg_p} ({CONFIG_ENV}) is not a YAML mapping")
    return cfg_p, cfg


def vault_for(cfg_p, cfg):
    """The raw vault value and where it came from, or a loud refusal when unset."""
    if cfg_p is not None:
        vd = cfg.get("vault_dir")
        if not vd:
            sys.exit(f"portfolio not configured: set vault_dir in {cfg_p} ({CONFIG_ENV})")
        return vd, f"{cfg_p} ({CONFIG_ENV})"
    try:
        vault, source = _config.vault_setting()
    except _config.ConfigError as e:
        sys.exit(f"portfolio not configured: {e}")
    if vault is None:
        sys.exit("portfolio not configured: no vault is set — set $OBSIDIAN_VAULT_PATH "
                 "or default_vault in obsidian-wiki's config.json")
    return vault, source


def registry_for(cfg_p, cfg):
    """SECURITY_REGISTRY, else the overriding config's `registry:` key — so an
    overriding config's own registry is honoured — else the plugin's location."""
    explicit = (os.environ.get(REGISTRY_ENV) or "").strip()
    if explicit:
        return Path(explicit).expanduser(), REGISTRY_ENV
    if cfg_p is not None and isinstance(cfg.get("registry"), str) and cfg["registry"].strip():
        return Path(cfg["registry"].strip()).expanduser(), f"{cfg_p} ({CONFIG_ENV})"
    try:
        return _config.registry_path(), "the plugin's registry location"
    except _config.ConfigError as e:
        sys.exit(f"portfolio not configured: {e}")


def load_env():
    cfg_p, cfg = config_for()
    vd, vault_source = vault_for(cfg_p, cfg)
    reg_p, reg_source = registry_for(cfg_p, cfg)
    # A missing or malformed registry is REFUSED, never read as an empty or smaller
    # portfolio: the JSON printed here is what the rebuild writes the security
    # dashboard from, and a missing project would render as "nothing has been
    # audited". The checks are the one registry validator's, not restated here.
    projects = _rebuild().load_projects(path=reg_p, source=reg_source)
    # Set-but-unreachable is REFUSED, never created — a missing vault is not an
    # empty vault. This scan only READS <vault>/…/security/history.jsonl, but its
    # JSON is what the rebuild writes the security dashboard from, and an
    # unreachable vault would hand that writer a full set of "no history recorded"
    # projects. `?` for unmeasured and `0` for clean are different answers;
    # refusing here is what keeps them different.
    vault = _require_vault(vd, vault_source)
    return vault, projects


def _read_runs(path):
    """Every parseable run record, oldest first. A malformed LINE is skipped and
    counted; a malformed FILE raises (the caller records couldnt_assess). Losing
    one line must not discard a project's whole history."""
    runs, bad = [], 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if isinstance(rec, dict) and rec.get("run_id"):
                runs.append(rec)
            else:
                bad += 1
    runs.sort(key=lambda r: str(r.get("run_id")))
    return runs, bad


def _sev(counts, *names):
    """A severity count, or None when it was not recorded. Never coerces a
    missing value to 0 — see the module docstring."""
    if not isinstance(counts, dict):
        return None
    for n in names:
        for key in (n, n.upper(), n.lower(), n.capitalize()):
            if key in counts and isinstance(counts[key], (int, float)):
                return int(counts[key])
    return None


def _age_days(run, now):
    """Days since the run, from finished_at/started_at, else the run_id stamp."""
    for field in ("finished_at", "started_at"):
        v = run.get(field)
        if isinstance(v, str):
            try:
                d = datetime.fromisoformat(v.replace("Z", "+00:00"))
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                return max(0, (now - d).days)
            except ValueError:
                pass
    rid = str(run.get("run_id") or "")
    try:
        d = datetime.strptime(rid[:13], "%Y%m%d-%H%M").replace(tzinfo=timezone.utc)
        return max(0, (now - d).days)
    except ValueError:
        return None


def _trend(runs):
    """Direction of open CRITICAL+HIGH over the last TREND_WINDOW runs.

    Only runs that actually recorded the counts are compared — an unrecorded run
    is skipped rather than read as zero. Fewer than two comparable points means
    no trend, not a flat one.
    """
    pts = []
    for r in runs[-TREND_WINDOW:]:
        c = _sev(r.get("counts"), "critical")
        h = _sev(r.get("counts"), "high")
        if c is None and h is None:
            continue
        pts.append((c or 0) + (h or 0))
    if len(pts) < 2:
        return None
    if pts[-1] > pts[0]:
        return "up"
    if pts[-1] < pts[0]:
        return "down"
    return "flat"


def scan_project(proj, vault, now):
    home = vault / "Portfolio" / proj["area"] / proj["name"]
    hist = home / "security" / "history.jsonl"
    base = {"name": proj["name"], "area": proj["area"], "path": proj.get("path")}
    if not hist.exists():
        reports = home / "security" / "reports"
        return {**base, "never_audited": True,
                # A reports dir with no history means an older layout or a
                # partially-written state — worth saying, not worth guessing at.
                "note": "has security/reports but no history.jsonl"
                        if reports.is_dir() else None}
    runs, bad_lines = _read_runs(hist)
    if not runs:
        return {**base, "never_audited": True,
                "note": f"history.jsonl present but no usable records "
                        f"({bad_lines} malformed line(s))"}
    last = runs[-1]
    deltas = last.get("deltas") if isinstance(last.get("deltas"), dict) else {}
    counts = last.get("counts") if isinstance(last.get("counts"), dict) else {}
    accepted = deltas.get("accepted")
    total_open = deltas.get("total_open")
    if not isinstance(accepted, int):
        accepted = None
    if not isinstance(total_open, int):
        total_open = None
    return {
        **base,
        "never_audited": False,
        "runs": len(runs),
        "malformed_lines": bad_lines,
        "last_run_id": last.get("run_id"),
        # `mode` is passed through verbatim, including values this script does
        # not know — the vocabulary belongs to the producer, not here.
        "mode": last.get("mode"),
        "code_verified": last.get("mode") != "feeds",
        "age_days": _age_days(last, now),
        "plugin_version": last.get("plugin_version"),
        "critical": _sev(counts, "critical"),
        "high": _sev(counts, "high"),
        "medium": _sev(counts, "medium"),
        "low": _sev(counts, "low"),
        "total_open": total_open,
        "accepted": accepted,
        # "open and not currently suppressed"; None unless BOTH are known
        "unsuppressed_open": (total_open - accepted)
        if isinstance(total_open, int) and isinstance(accepted, int) else None,
        "trend": _trend(runs),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="security-scan.py",
        description="Sweep every enabled registry project's security/history.jsonl in "
                    "the vault into one JSON document for security-rollup.py.",
        epilog=HELP_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args(argv)
    vault, projects = load_env()
    now = datetime.now(timezone.utc)
    out = {"generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "vault_dir": str(vault), "supported_schema": SUPPORTED_SCHEMA,
           "projects": [], "couldnt_assess": []}
    for p in sorted(projects, key=lambda x: (x.get("area", ""), x.get("name", ""))):
        # An entry that keeps its records in its repo has no vault home: listed with
        # the reason, never read from a vault folder left at its old path.
        if _rebuild().records_in_repo(p):
            out["couldnt_assess"].append({"name": p.get("name"), "area": p.get("area"),
                                          "reason": _rebuild().OPTED_OUT})
            continue
        try:
            out["projects"].append(scan_project(p, vault, now))
        except Exception as e:                     # never abort the sweep
            out["couldnt_assess"].append(
                {"name": p.get("name"), "area": p.get("area"),
                 "reason": f"{type(e).__name__}: {e}"})
    json.dump(out, sys.stdout, indent=1, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
