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
for token in (
    "CODEX_RESPONSES_PROXY_RELEASE_ASSET_SIGNING_KEY",
    "CODEX_RESPONSES_PROXY_RELEASE_ASSET_TRUST",
    "CODEX_RESPONSES_PROXY_RELEASE_ASSET_DIR",
    "build-gitlab-native-asset",
    "docker: { platform: linux/amd64 }",
):
    if token not in text:
        raise SystemExit(f"GitLab release job does not receive {token}")
PYTHON

fixture="$tmp/native-assets"
store="$tmp/gitlab-store"
mkdir -p "$fixture" "$store"
key="$tmp/release-key"
ssh-keygen -q -t ed25519 -N '' -f "$key"
PYTHONPATH="$root" VERSION="$version" FIXTURE="$fixture" python3 - <<'PYTHON'
import os
from pathlib import Path

from tools.release import product_assets as assets

root = Path(os.environ["FIXTURE"])
version = os.environ["VERSION"]
release = {}
for platform in assets.RELEASE_PLATFORMS:
    executable = "codex-responses-proxy.exe" if platform.startswith("windows-") else "codex-responses-proxy"
    files = {executable: assets.ArchiveFile(platform.encode(), 0o755)}
    archive_name = assets.archive_name(version, platform)
    archive = assets.archive_bytes(files, version, platform)
    release[archive_name] = archive
    release[assets.manifest_name(platform)] = assets.asset_manifest(
        version=version,
        platform=platform,
        archive_name=archive_name,
        archive=archive,
        files=files,
    )
release[assets.CHECKSUM_NAME] = assets.checksums(release)
for name, content in release.items():
    (root / name).write_bytes(content)
PYTHON
(cd "$fixture" && ssh-keygen -Y sign -q -f "$key" -n codex-responses-proxy-release SHA256SUMS)
public_key=$(cat "$key.pub")
trust="codex-responses-proxy-release namespaces=\"codex-responses-proxy-release\" $public_key"

mock_curl="$tmp/curl"
log="$tmp/curl.log"
cat > "$mock_curl" <<'EOF'
#!/bin/sh
set -eu
output=
method=GET
upload=
write_out=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output) output=$2; shift 2 ;;
    --request) method=$2; shift 2 ;;
    --header) shift 2 ;;
    --data) shift 2 ;;
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
      FIXTURE="${CODEX_RESPONSES_PROXY_TEST_FIXTURE:?}" TAG="${CODEX_RESPONSES_PROXY_TEST_TAG:?}" \
        python3 - "$output" <<'PYTHON'
import json
import os
import sys
from pathlib import Path

names = sorted(path.name for path in Path(os.environ["FIXTURE"]).iterdir())
Path(sys.argv[1]).write_text(json.dumps({
    "tag_name": os.environ["TAG"],
    "name": f"Codex Responses Proxy {os.environ['TAG']}",
    "assets": {"links": [{"name": name} for name in names]},
}))
PYTHON
    fi
    code=200
    ;;
  *) echo "unexpected curl URL: $url" >&2; exit 1 ;;
esac
if [ -n "$write_out" ]; then printf %s "$code"; fi
EOF
chmod +x "$mock_curl"

run() {
  mode=$1
  PATH="$tmp:$PATH" PYTHON="$(command -v python3)" PYTHONPATH="$root" \
    CODEX_RESPONSES_PROXY_TEST_CURL_LOG="$log" \
    CODEX_RESPONSES_PROXY_TEST_CURL_MODE="$mode" \
    CODEX_RESPONSES_PROXY_TEST_FIXTURE="$fixture" \
    CODEX_RESPONSES_PROXY_TEST_STORE="$store" \
    CODEX_RESPONSES_PROXY_TEST_TAG="$tag" \
    CODEX_RESPONSES_PROXY_RELEASE_ASSET_DIR="$fixture" \
    CODEX_RESPONSES_PROXY_RELEASE_ASSET_SIGNING_KEY="$key" \
    CODEX_RESPONSES_PROXY_RELEASE_ASSET_TRUST="$trust" \
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
if grep -Fi github "$log" >/dev/null || grep -Fi github "$script" >/dev/null; then
  echo 'GitLab publisher retains a GitHub dependency' >&2
  exit 1
fi
grep -F 'POST https://gitlab.example.test/api/v4/projects/453/releases' "$log" >/dev/null
grep -F "GET https://gitlab.example.test/api/v4/projects/453/releases/$tag" "$log" >/dev/null
for file in "$fixture"/*; do
  name=$(basename "$file")
  grep -F "PUT https://gitlab.example.test/api/v4/projects/453/packages/generic/codex-responses-proxy/$tag/$name" "$log" >/dev/null
done

echo 'GitLab release publication contract: OK'
