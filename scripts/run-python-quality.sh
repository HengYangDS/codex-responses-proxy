#!/bin/sh
# Run the repository-owned Python quality gate used by both Forge projections.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python=${PYTHON:-python3}
ruff=${RUFF:-ruff}
ty=${TY:-ty}

cd "$root"

if [ -z "${COVERAGE_FILE:-}" ]; then
  coverage_dir=$(mktemp -d "${TMPDIR:-/tmp}/codex-dmx-proxy-coverage.XXXXXX")
  COVERAGE_FILE="$coverage_dir/.coverage"
  export COVERAGE_FILE
  trap 'rm -rf "$coverage_dir"' EXIT HUP INT TERM
fi

python_path=$(command -v "$python") || {
  echo "Python quality interpreter is unavailable: $python" >&2
  exit 2
}
ruff_path=$(command -v "$ruff") || {
  echo "Ruff is unavailable: $ruff" >&2
  exit 2
}
ty_path=$(command -v "$ty") || {
  echo "ty is unavailable: $ty" >&2
  exit 2
}
coverage_version=$("$python_path" -m coverage --version 2>/dev/null | sed -n '1p') || {
  echo "coverage.py is unavailable to $python" >&2
  exit 2
}
[ "$coverage_version" = "Coverage.py, version 7.13.5 with C extension" ] || {
  echo "coverage.py 7.13.5 is required" >&2
  exit 2
}
[ "$($ruff_path --version)" = "ruff 0.16.0" ] || {
  echo "Ruff 0.16.0 is required" >&2
  exit 2
}
case "$($ty_path --version)" in
  "ty 0.0.64"|"ty 0.0.64 "*) ;;
  *) echo "ty 0.0.64 is required" >&2; exit 2 ;;
esac

set -- $(
  "$python_path" - <<'PY'
import tomllib
from pathlib import Path

policy = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["tool"]["codex-dmx-proxy"]["quality"]
for key in ("source-roots", "test-roots"):
    for path in policy[key]:
        print(path)
PY
)

# Ruff owns repository-wide deterministic source shape, including tests and
# governance scripts. The structural audit, type checker, and coverage gate own
# their narrower semantic scopes below.
"$ruff_path" check .
"$ruff_path" format --check .
"$python_path" scripts/check_quality.py
"$ty_path" check \
  --python "$python_path" \
  --python-version 3.12 \
  --python-platform all \
  --error-on-warning \
  --no-progress \
  "$@"

"$python_path" -m coverage erase
"$python_path" scripts/run-python-tests.py --coverage
"$python_path" -m coverage report
"$python_path" scripts/check_branch_coverage.py
