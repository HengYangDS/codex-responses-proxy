#!/bin/sh
# Publish exact assets and the immutable provider-native GitLab Release record.
set -eu

: "${CI_API_V4_URL:?CI_API_V4_URL is required}"
: "${CI_PROJECT_ID:?CI_PROJECT_ID is required}"
: "${CI_COMMIT_TAG:?CI_COMMIT_TAG is required}"
: "${CI_JOB_TOKEN:?CI_JOB_TOKEN is required}"

case "$CI_API_V4_URL" in http://*|https://*) ;; *) echo "CI_API_V4_URL must be an HTTP(S) URL" >&2; exit 2 ;; esac
case "$CI_PROJECT_ID" in *[!0-9]*|'') echo "CI_PROJECT_ID must be numeric" >&2; exit 2 ;; esac
case "$CI_COMMIT_TAG" in v[0-9]*.[0-9]*.[0-9]*) ;; *) echo "CI_COMMIT_TAG must be a v<semver> tag" >&2; exit 2 ;; esac

payload=$(mktemp "${TMPDIR:-/tmp}/codex-responses-proxy-release.XXXXXX")
response=$(mktemp "${TMPDIR:-/tmp}/codex-responses-proxy-release-response.XXXXXX")
assets=$(mktemp -d "${TMPDIR:-/tmp}/codex-responses-proxy-assets.XXXXXX")
cleanup() { rm -f "$payload" "$response"; rm -rf "$assets"; }
trap cleanup EXIT HUP INT TERM

python_bin=${PYTHON:-$(command -v python3 || true)}
[ -n "$python_bin" ] || { echo "python3 is required for GitLab release metadata" >&2; exit 2; }
"$python_bin" -m tools.release.assets --output "$assets"
version=${CI_COMMIT_TAG#v}
archive="$assets/codex-responses-proxy-$version.tar.gz"
checksums="$assets/SHA256SUMS"
asset_base="$CI_API_V4_URL/projects/$CI_PROJECT_ID/packages/generic/codex-responses-proxy/$CI_COMMIT_TAG"

upload() {
  file=$1
  name=$(basename "$file")
  url="$asset_base/$name"
  status=$(curl --silent --show-error --output "$response" --write-out '%{http_code}' \
    --header "JOB-TOKEN: $CI_JOB_TOKEN" --upload-file "$file" "$url" || true)
  case "$status" in 200|201|409) ;; *) echo "GitLab release asset upload failed: $name" >&2; exit 1 ;; esac
  curl --fail --silent --show-error --location --header "JOB-TOKEN: $CI_JOB_TOKEN" \
    --output "$assets/downloaded-$name" "$url"
  cmp "$file" "$assets/downloaded-$name" || {
    echo "GitLab release asset differs after upload: $name" >&2
    exit 1
  }
}
upload "$archive"
upload "$checksums"

CI_COMMIT_TAG="$CI_COMMIT_TAG" CODEX_RESPONSES_PROXY_ASSET_BASE="$asset_base" \
  "$python_bin" - "$payload" <<'PYTHON'
import json
import os
import sys

tag = os.environ["CI_COMMIT_TAG"]
base = os.environ["CODEX_RESPONSES_PROXY_ASSET_BASE"]
version = tag.removeprefix("v")
links = [
    {"name": f"codex-responses-proxy-{version}.tar.gz", "url": f"{base}/codex-responses-proxy-{version}.tar.gz", "link_type": "package"},
    {"name": "SHA256SUMS", "url": f"{base}/SHA256SUMS", "link_type": "package"},
]
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump({
        "tag_name": tag,
        "name": f"Codex Responses Proxy {tag}",
        "description": "Provider-native source release. See CHANGELOG.md for user-relevant changes.",
        "assets": {"links": links},
    }, handle)
PYTHON

endpoint="$CI_API_V4_URL/projects/$CI_PROJECT_ID/releases"
status=$(curl --silent --show-error --output "$response" --write-out '%{http_code}' \
  --request POST --header "JOB-TOKEN: $CI_JOB_TOKEN" --header 'Content-Type: application/json' \
  --data @"$payload" "$endpoint" || true)
case "$status" in
  2??) echo "GitLab provider-native release created: $CI_COMMIT_TAG" ;;
  409)
    status=$(curl --silent --show-error --output "$response" --write-out '%{http_code}' \
      --header "JOB-TOKEN: $CI_JOB_TOKEN" "$endpoint/$CI_COMMIT_TAG" || true)
    [ "$status" = 200 ] || { echo "GitLab release lookup failed" >&2; exit 1; }
    CI_COMMIT_TAG="$CI_COMMIT_TAG" "$python_bin" - "$response" <<'PYTHON'
import json
import os
import sys

release = json.load(open(sys.argv[1], encoding="utf-8"))
tag = os.environ["CI_COMMIT_TAG"]
version = tag.removeprefix("v")
names = sorted(link.get("name") for link in release.get("assets", {}).get("links", []))
expected = sorted((f"codex-responses-proxy-{version}.tar.gz", "SHA256SUMS"))
if release.get("tag_name") != tag or release.get("name") != f"Codex Responses Proxy {tag}" or names != expected:
    raise SystemExit("existing GitLab release does not match immutable release identity")
PYTHON
    echo "GitLab provider-native release already matches: $CI_COMMIT_TAG"
    ;;
  *) cat "$response" >&2 2>/dev/null || true; echo "GitLab release publication failed with HTTP ${status:-transport-error}" >&2; exit 1 ;;
esac
