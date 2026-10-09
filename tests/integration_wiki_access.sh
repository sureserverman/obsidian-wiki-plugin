#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Only implemented integration families run; unknown/empty explicit selectors fail.
python3 - <<'PY'
import runpy, sys, unittest
module = runpy.run_path('tests/wiki_access_cases.py')
names = [name for name, cls in module.items() if name.endswith('IntegrationCases')
         and isinstance(cls, type) and issubclass(cls, unittest.TestCase)]
if not names:
    sys.exit('no implemented integration families')
sys.argv = ['tests/wiki_access_cases.py', *names]
runpy.run_path(sys.argv[0], run_name='__main__')
PY
