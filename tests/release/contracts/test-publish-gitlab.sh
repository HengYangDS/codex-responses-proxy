#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
script="$root/tools/release/publish-gitlab.sh"
ci="$root/.gitlab-ci.yml"
policy="$root/tests/fixtures/publication-policy.toml"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/codex-responses-proxy-gitlab-release.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
version=$(git -C "$root" show HEAD:VERSION | tr -d '\r\n')
tag="v$version"

python3 - "$ci" "$policy" <<'PYTHON'
import re
import sys
import tomllib
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
policy = tomllib.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
match = re.search(r"(?m)^publish-gitlab-release:\n(?:^  .+\n)*?^  needs:\n(?P<needs>(?:^    - [^\n]+\n)+)", text)
if match is None:
    raise SystemExit("GitLab release job has no explicit required-job dependencies")
actual = tuple(line.removeprefix("    - ") for line in match["needs"].splitlines())
expected = tuple(job for job in policy["gitlab"]["required-jobs"] if job != "publish-gitlab-release")
if actual != expected:
    raise SystemExit(f"GitLab release dependencies differ from publication policy: {actual!r}")
PYTHON

mock_curl="$tmp/curl"
log="$tmp/curl.log"
store="$tmp/store"
mkdir -p "$store"
cat > "$mock_curl" <<'EOF'
#!/bin/sh
set -eu
output=
method=GET
upload=
data=
write_out=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output) output=$2; shift 2 ;;
    --request) method=$2; shift 2 ;;
    --header) shift 2 ;;
    --data) data=$2; shift 2 ;;
    --write-out) write_out=$2; shift 2 ;;
    --upload-file) upload=$2; method=PUT; shift 2 ;;
    --fail|--silent|--show-error|--location) shift ;;
    *) url=$1; shift ;;
  esac
done
printf '%s %s\n' "$method" "${url:-}" >> "${CODEX_RESPONSES_PROXY_TEST_CURL_LOG:?}"
name=${url##*/}
case "$url" in
  */packages/generic/*)
    target="${CODEX_RESPONSES_PROXY_TEST_STORE:?}/$name"
    if [ -n "$upload" ]; then cp "$upload" "$target"; code=201
    else cp "$target" "$output"; code=200
    fi
    ;;
  */releases)
    case "${CODEX_RESPONSES_PROXY_TEST_CURL_MODE:?}" in
      create) printf '{}' > "$output"; code=201 ;;
      existing|mismatch) printf '{}' > "$output"; code=409 ;;
    esac
    ;;
  */releases/*)
    if [ "${CODEX_RESPONSES_PROXY_TEST_CURL_MODE:?}" = mismatch ]; then
      printf '{"tag_name":"%s","name":"wrong"}' "${CODEX_RESPONSES_PROXY_TEST_TAG:?}" > "$output"
    else
      printf '{"tag_name":"%s","name":"Codex Responses Proxy %s","assets":{"links":[{"name":"codex-responses-proxy-%s.tar.gz"},{"name":"SHA256SUMS"}]}}' \
        "${CODEX_RESPONSES_PROXY_TEST_TAG:?}" "${CODEX_RESPONSES_PROXY_TEST_TAG:?}" \
        "${CODEX_RESPONSES_PROXY_TEST_VERSION:?}" > "$output"
    fi
    code=200
    ;;
esac
if [ -n "$write_out" ]; then
  printf %s "$code"
fi
EOF
chmod +x "$mock_curl"

run() {
  mode=$1
  PATH="$tmp:$PATH" PYTHON="$(command -v python3)" CODEX_RESPONSES_PROXY_TEST_CURL_LOG="$log" CODEX_RESPONSES_PROXY_TEST_CURL_MODE="$mode" CODEX_RESPONSES_PROXY_TEST_STORE="$store" CODEX_RESPONSES_PROXY_TEST_TAG="$tag" CODEX_RESPONSES_PROXY_TEST_VERSION="$version" \
    CI_API_V4_URL=https://gitlab.example.test/api/v4 CI_PROJECT_ID=453 \
    CI_COMMIT_TAG="$tag" CI_JOB_TOKEN=redacted \
    sh "$script"
}

run create > "$tmp/create.out"
grep -Fx "GitLab provider-native release created: $tag" "$tmp/create.out" >/dev/null
run existing > "$tmp/existing.out"
grep -Fx "GitLab provider-native release already matches: $tag" "$tmp/existing.out" >/dev/null
if run mismatch >/dev/null 2>&1; then
  echo 'publisher accepted a mismatched immutable release record' >&2
  exit 1
fi
grep -F 'POST https://gitlab.example.test/api/v4/projects/453/releases' "$log" >/dev/null
grep -F "GET https://gitlab.example.test/api/v4/projects/453/releases/$tag" "$log" >/dev/null
grep -F "PUT https://gitlab.example.test/api/v4/projects/453/packages/generic/codex-responses-proxy/$tag/codex-responses-proxy-$version.tar.gz" "$log" >/dev/null
grep -F "PUT https://gitlab.example.test/api/v4/projects/453/packages/generic/codex-responses-proxy/$tag/SHA256SUMS" "$log" >/dev/null

echo 'GitLab release publication contract: OK'
