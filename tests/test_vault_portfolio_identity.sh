#!/usr/bin/env bash
# test_vault_portfolio_identity.sh — the Cursor and OpenCode ports declare their id.
#
# Claude Code and Codex record the marketplace a plugin came from; Cursor and OpenCode
# do not, so a package for them carries agent-plugin.json, {"id": "<plugin>@<marketplace>"},
# and planning's host-status.py reads it. A port without one shows up as
# vault-portfolio@local, and a cutover that expects vault-portfolio@obsidian-wiki fails.
# The id must name this repo's marketplace, so it is read from marketplace.json, not typed.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

python3 -I - "$ROOT" <<'PY'
import json, sys
from pathlib import Path

root = Path(sys.argv[1])
market = json.loads((root / ".claude-plugin/marketplace.json").read_text())["name"]
want = {"id": f"vault-portfolio@{market}"}
fails = []
for host in ("cursor", "opencode"):
    for rel in (f"src/vault-portfolio/hosts/{host}/add/agent-plugin.json",
                f"ports/{host}/vault-portfolio/agent-plugin.json"):
        path = root / rel
        try:
            got = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            fails.append(f"{rel}: {exc}")
            continue
        if got != want:
            fails.append(f"{rel}: declares {got}, want {want}")
for f in fails:
    print(f"FAIL: {f}", file=sys.stderr)
if fails:
    sys.exit(1)
print(f"  ok: the cursor and opencode ports declare {want['id']}")
print("ALL OK")
PY
