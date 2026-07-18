#!/bin/sh
# Create the provider-native GitLab release record without relying on the
# deprecated release-cli helper that may be absent from a Docker runner.
set -eu

: "${CI_API_V4_URL:?CI_API_V4_URL is required}"
: "${CI_PROJECT_ID:?CI_PROJECT_ID is required}"
: "${CI_COMMIT_TAG:?CI_COMMIT_TAG is required}"
: "${CI_JOB_TOKEN:?CI_JOB_TOKEN is required}"

case "$CI_API_V4_URL" in http://*|https://*) ;; *) echo "CI_API_V4_URL must be an HTTP(S) URL" >&2; exit 2 ;; esac
case "$CI_PROJECT_ID" in *[!0-9]*|'') echo "CI_PROJECT_ID must be numeric" >&2; exit 2 ;; esac
case "$CI_COMMIT_TAG" in v[0-9]*.[0-9]*.[0-9]*) ;; *) echo "CI_COMMIT_TAG must be a v<semver> tag" >&2; exit 2 ;; esac

payload=$(mktemp "${TMPDIR:-/tmp}/codex-dmx-proxy-release.XXXXXX")
response=$(mktemp "${TMPDIR:-/tmp}/codex-dmx-proxy-release-response.XXXXXX")
cleanup() { rm -f "$payload" "$response"; }
trap cleanup EXIT HUP INT TERM

python_bin=${PYTHON:-}
if [ -z "$python_bin" ]; then
  python_bin=$(command -v python3 || true)
fi
[ -n "$python_bin" ] || { echo "python3 is required for GitLab release metadata" >&2; exit 2; }

CI_COMMIT_TAG="$CI_COMMIT_TAG" "$python_bin" - "$payload" <<'PYTHON'
import json
import os
import sys

tag = os.environ["CI_COMMIT_TAG"]
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(
        {
            "tag_name": tag,
            "name": f"Codex DMX Proxy {tag}",
            "description": "Provider-native source release. See CHANGELOG.md for user-relevant changes.",
        },
        handle,
    )
PYTHON

endpoint="$CI_API_V4_URL/projects/$CI_PROJECT_ID/releases"
status=$(curl --silent --show-error --output "$response" --write-out '%{http_code}' \
  --request POST --header "JOB-TOKEN: $CI_JOB_TOKEN" --header 'Content-Type: application/json' \
  --data @"$payload" "$endpoint" || true)
case "$status" in
  2??)
    echo "GitLab provider-native release created: $CI_COMMIT_TAG"
    exit 0
    ;;
  409)
    status=$(curl --silent --show-error --output "$response" --write-out '%{http_code}' \
      --header "JOB-TOKEN: $CI_JOB_TOKEN" "$endpoint/$CI_COMMIT_TAG" || true)
    case "$status" in
      200)
        CI_COMMIT_TAG="$CI_COMMIT_TAG" "$python_bin" - "$response" <<'PYTHON'
import json
import os
import sys

release = json.load(open(sys.argv[1], encoding="utf-8"))
tag = os.environ["CI_COMMIT_TAG"]
if release.get("tag_name") != tag or release.get("name") != f"Codex DMX Proxy {tag}":
    raise SystemExit("existing GitLab release does not match immutable release identity")
PYTHON
        echo "GitLab provider-native release already matches: $CI_COMMIT_TAG"
        exit 0
        ;;
    esac
    ;;
esac
cat "$response" >&2 2>/dev/null || true
echo "GitLab release publication failed with HTTP ${status:-transport-error}" >&2
exit 1
