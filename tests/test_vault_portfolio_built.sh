#!/usr/bin/env bash
# test_vault_portfolio_built.sh — plugins/vault-portfolio is exactly what its
# sources build to.
#
# plugins/vault-portfolio is generated from src/vault-portfolio (core/ plus
# hosts/claude/add/) by the planning repo's build.py, which this repo's CI does
# not have. So the drift a missed rebuild or a hand edit of a generated file
# leaves behind is checked here directly: the same file set, byte-identical,
# except plugin.json, which is the source plus `"version"` from VERSION.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="src/vault-portfolio"
OUT="plugins/vault-portfolio"

python3 -I - "$ROOT" "$SRC" "$OUT" <<'PY'
import json, subprocess, sys
from pathlib import Path

root, src, out = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
MANIFEST = ".claude-plugin/plugin.json"

def files(rel):
    r = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others",
                        "--exclude-standard", "--", rel], capture_output=True, check=True)
    base = Path(rel)
    return {Path(p).relative_to(base).as_posix(): root / p
            for p in r.stdout.decode().split("\0")
            if p and (root / p).is_file() and "__pycache__" not in Path(p).parts}

want = {**files(f"{src}/core"), **files(f"{src}/hosts/claude/add")}
have = files(out)
fails = [f"missing from {out}: {p}" for p in sorted(set(want) - set(have))]
fails += [f"not built from any source: {out}/{p}" for p in sorted(set(have) - set(want))]
for p in sorted(set(want) & set(have)):
    if p == MANIFEST:
        version = (root / src / "VERSION").read_text().strip()
        source = json.loads(want[p].read_text())
        built = json.loads(have[p].read_text())
        if "version" in source:
            fails.append(f"{src}: the source plugin.json carries a version; VERSION owns it")
        if built.get("version") != version or {k: v for k, v in built.items() if k != "version"} != source:
            fails.append(f"{out}/{p} is not the source plus version {version}")
    elif want[p].read_bytes() != have[p].read_bytes():
        fails.append(f"{out}/{p} differs from its source")
for f in fails:
    print(f"FAIL: {f}", file=sys.stderr)
if not want:
    print("FAIL: no source files found", file=sys.stderr)
    sys.exit(1)
if fails:
    print(f"{len(fails)} failure(s); rebuild with the planning repo's build/build.py --root {src} "
          "--host claude", file=sys.stderr)
    sys.exit(1)
print(f"  ok: {out} matches its {len(want)} source files")
print("ALL OK")
PY
