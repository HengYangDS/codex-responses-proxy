#!/bin/sh
# Run the repository-owned Python quality gate used by both Forge projections.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python=${PYTHON:-python3}
ruff=${RUFF:-ruff}
ty=${TY:-ty}

cd "$root"

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
"$python_path" -m coverage --version >/dev/null 2>&1 || {
  echo "coverage.py is unavailable to $python" >&2
  exit 2
}
[ "$($ruff_path --version)" = "ruff 0.16.0" ] || {
  echo "Ruff 0.16.0 is required" >&2
  exit 2
}
case "$($ty_path --version)" in
  "ty 0.0.56"|"ty 0.0.56 "*) ;;
  *) echo "ty 0.0.56 is required" >&2; exit 2 ;;
esac

set -- $(
  "$python_path" - <<'PY'
import tomllib
from pathlib import Path

policy = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["tool"]["codex-dmx-proxy"]["quality"]
for path in policy["type-roots"]:
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
