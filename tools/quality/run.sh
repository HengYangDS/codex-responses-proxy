#!/bin/sh
# Run the repository-owned Python quality gate used by both Forge projections.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
python=${PYTHON:-python3}
ruff=${RUFF:-ruff}
ty=${TY:-ty}

resolve_versioned_tool() {
  requested=$1
  expected=$2
  label=$3
  case "$requested" in
    */*)
      [ -x "$requested" ] && version_matches "$requested" "$expected" || {
        echo "$label ${expected#* } is required" >&2
        return 2
      }
      printf '%s\n' "$requested"
      ;;
    *)
      old_ifs=$IFS
      IFS=:
      for directory in $PATH; do
        [ -n "$directory" ] || directory=.
        candidate=$directory/$requested
        if [ -x "$candidate" ] && version_matches "$candidate" "$expected"; then
          IFS=$old_ifs
          printf '%s\n' "$candidate"
          return 0
        fi
      done
      IFS=$old_ifs
      echo "$label ${expected#* } is required" >&2
      return 2
      ;;
  esac
}

version_matches() {
  output=$("$1" --version 2>/dev/null) || return 1
  case "$output" in
    "$2"|"$2 "?*) return 0 ;;
    *) return 1 ;;
  esac
}

cd "$root"

if [ -z "${COVERAGE_FILE:-}" ]; then
  coverage_dir=$(mktemp -d "${TMPDIR:-/tmp}/codex-responses-proxy-coverage.XXXXXX")
  COVERAGE_FILE="$coverage_dir/.coverage"
  export COVERAGE_FILE
  trap 'rm -rf "$coverage_dir"' EXIT HUP INT TERM
fi

python_path=$(command -v "$python") || {
  echo "Python quality interpreter is unavailable: $python" >&2
  exit 2
}
ruff_path=$(resolve_versioned_tool "$ruff" "ruff 0.16.1" "Ruff") || exit $?
ty_path=$(resolve_versioned_tool "$ty" "ty 0.0.65" "ty") || exit $?
coverage_version=$("$python_path" -m coverage --version 2>/dev/null | sed -n '1p') || {
  echo "coverage.py is unavailable to $python" >&2
  exit 2
}
[ "$coverage_version" = "Coverage.py, version 7.13.5 with C extension" ] || {
  echo "coverage.py 7.13.5 is required" >&2
  exit 2
}
set -- $(
  "$python_path" - <<'PY'
import tomllib
from pathlib import Path

policy = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["tool"]["codex-responses-proxy"]["quality"]
for key in ("source-roots", "test-roots"):
    for path in policy[key]:
        print(path)
PY
)

# Ruff owns repository-wide deterministic source shape, including tests and
# governance scripts. The structural audit, type checker, and coverage gate own
# their narrower semantic scopes below.
"$ruff_path" check --no-cache .
"$ruff_path" format --no-cache --check .
"$python_path" tools/quality/portability.py
"$python_path" tools/quality/repository.py
"$ty_path" check \
  --python "$python_path" \
  --python-version 3.12 \
  --python-platform all \
  --error-on-warning \
  --no-progress \
  "$@"

"$python_path" -m coverage erase
"$python_path" tools/quality/tests.py --coverage
"$python_path" -m coverage report
"$python_path" tools/quality/branch_coverage.py
