#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Compile source in memory: recursive coverage without writing package bytecode.
python3 - <<'PYTHON_SYNTAX'
from pathlib import Path
paths=sorted(p for root in ('plugins','ports','tests') for p in Path(root).rglob('*.py'))
if not paths:raise SystemExit('no Python sources discovered')
for path in paths:compile(path.read_bytes(),str(path),'exec')
print(f'Python syntax: {len(paths)} sources PASS')
PYTHON_SYNTAX
