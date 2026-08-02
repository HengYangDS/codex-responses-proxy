#!/bin/sh
# Reproduce the complete quality gate in the repository-owned locked environment.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root"

uv=${UV:-uv}
quality_python=${PYTHON:-python3.12}
export PYTHONNOUSERSITE=1 UV_NO_PROGRESS=1

"$uv" sync --locked --only-group quality --python "$quality_python" --no-install-project

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) bin=.venv/Scripts ;;
  *) bin=.venv/bin ;;
esac
python=$bin/python
ruff=$bin/ruff
ty=$bin/ty

if [ -z "${COVERAGE_FILE:-}" ]; then
  coverage_dir=$(mktemp -d "${TMPDIR:-/tmp}/codex-responses-proxy-coverage.XXXXXX")
  COVERAGE_FILE="$coverage_dir/.coverage"
  export COVERAGE_FILE
  trap 'rm -rf "$coverage_dir"' EXIT HUP INT TERM
fi

set -- $(
  "$python" - <<'PY'
import tomllib
from pathlib import Path

policy = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["tool"]["codex-responses-proxy"]["quality"]
for key in ("source-roots", "test-roots"):
    print(*policy[key], sep="\n")
PY
)

"$ruff" check --no-cache .
"$ruff" format --no-cache --check .
"$python" tools/quality/portability.py
"$python" tools/quality/repository.py
"$ty" check \
  --python "$python" \
  --python-version 3.12 \
  --python-platform all \
  --error-on-warning \
  --no-progress \
  "$@"

"$python" -m coverage erase
"$python" tools/quality/tests.py --coverage
"$python" -m coverage report
"$python" tools/quality/branch_coverage.py
