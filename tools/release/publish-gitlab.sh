#!/bin/sh
# Publish one GitLab-native asset set without contacting another Forge.
set -eu

: "${CI_API_V4_URL:?CI_API_V4_URL is required}"
: "${CI_PROJECT_ID:?CI_PROJECT_ID is required}"
: "${CI_COMMIT_TAG:?CI_COMMIT_TAG is required}"
: "${CI_JOB_TOKEN:?CI_JOB_TOKEN is required}"
: "${CODEX_RESPONSES_PROXY_RELEASE_ASSET_DIR:?release asset directory is required}"
: "${CODEX_RESPONSES_PROXY_RELEASE_ASSET_SIGNING_KEY:?release signing key is required}"
: "${CODEX_RESPONSES_PROXY_RELEASE_ASSET_TRUST:?release asset trust is required}"

case "$CI_API_V4_URL" in http://*|https://*) ;; *) echo "CI_API_V4_URL must be an HTTP(S) URL" >&2; exit 2 ;; esac
case "$CI_PROJECT_ID" in *[!0-9]*|'') echo "CI_PROJECT_ID must be numeric" >&2; exit 2 ;; esac
case "$CI_COMMIT_TAG" in v[0-9]*.[0-9]*.[0-9]*) ;; *) echo "CI_COMMIT_TAG must be a v<semver> tag" >&2; exit 2 ;; esac

python_bin=${PYTHON:-$(command -v python3 || true)}
[ -n "$python_bin" ] || { echo "python3 is required for GitLab release publication" >&2; exit 2; }
command -v ssh-keygen >/dev/null 2>&1 || { echo "ssh-keygen is required" >&2; exit 2; }
source_assets=$CODEX_RESPONSES_PROXY_RELEASE_ASSET_DIR
[ -d "$source_assets" ] || { echo "release asset directory is unavailable" >&2; exit 2; }
[ -f "$CODEX_RESPONSES_PROXY_RELEASE_ASSET_SIGNING_KEY" ] || {
  echo "release signing key file is unavailable" >&2
  exit 2
}

work=$(mktemp -d "${TMPDIR:-/tmp}/codex-responses-proxy-gitlab-release.XXXXXX")
assets="$work/assets"
downloaded="$work/downloaded"
payload="$work/release.json"
response="$work/response.json"
anchor="$work/release-asset-trust"
mkdir -p "$assets" "$downloaded"
cleanup() { rm -rf "$work"; }
trap cleanup EXIT HUP INT TERM

cp "$source_assets"/* "$assets/"
printf '%s\n' "$CODEX_RESPONSES_PROXY_RELEASE_ASSET_TRUST" > "$anchor"
chmod 600 "$anchor"
rm -f "$assets/SHA256SUMS.sig"
(cd "$assets" && ssh-keygen -Y sign -q \
  -f "$CODEX_RESPONSES_PROXY_RELEASE_ASSET_SIGNING_KEY" \
  -n codex-responses-proxy-release SHA256SUMS)
principal=$(ssh-keygen -Y find-principals -s "$assets/SHA256SUMS.sig" \
  -f "$anchor" < "$assets/SHA256SUMS")
[ "$principal" = codex-responses-proxy-release ] || {
  echo "release asset signature principal is invalid" >&2
  exit 1
}
ssh-keygen -Y verify -f "$anchor" -I "$principal" \
  -n codex-responses-proxy-release -s "$assets/SHA256SUMS.sig" \
  < "$assets/SHA256SUMS"

verify_assets() {
  ASSET_DIR=$1 VERSION="${CI_COMMIT_TAG#v}" "$python_bin" - <<'PYTHON'
import os
from pathlib import Path
from tools.release import product_assets

root = Path(os.environ["ASSET_DIR"])
files = {path.name: path.read_bytes() for path in root.iterdir() if path.is_file()}
platforms = product_assets.release_platforms(set(files), os.environ["VERSION"])
product_assets.release_digests(files, os.environ["VERSION"], platforms)
PYTHON
}
verify_assets "$assets"

asset_base="$CI_API_V4_URL/projects/$CI_PROJECT_ID/packages/generic/codex-responses-proxy/$CI_COMMIT_TAG"
for file in "$assets"/*; do
  name=$(basename "$file")
  url="$asset_base/$name"
  status=$(curl --silent --show-error --output "$response" --write-out '%{http_code}' \
    --header "JOB-TOKEN: $CI_JOB_TOKEN" --upload-file "$file" "$url" || true)
  case "$status" in 200|201|409) ;; *) echo "GitLab release asset upload failed: $name" >&2; exit 1 ;; esac
  curl --fail --silent --show-error --location --header "JOB-TOKEN: $CI_JOB_TOKEN" \
    --output "$downloaded/$name" "$url"
  cmp "$file" "$downloaded/$name" || {
    echo "GitLab release asset differs after upload: $name" >&2
    exit 1
  }
done
verify_assets "$downloaded"

CI_COMMIT_TAG="$CI_COMMIT_TAG" CODEX_RESPONSES_PROXY_ASSET_BASE="$asset_base" \
  ASSET_DIR="$assets" "$python_bin" - "$payload" <<'PYTHON'
import json
import os
import sys
from pathlib import Path

tag = os.environ["CI_COMMIT_TAG"]
base = os.environ["CODEX_RESPONSES_PROXY_ASSET_BASE"]
names = sorted(path.name for path in Path(os.environ["ASSET_DIR"]).iterdir() if path.is_file())
links = [{"name": name, "url": f"{base}/{name}", "link_type": "package"} for name in names]
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
    CI_COMMIT_TAG="$CI_COMMIT_TAG" ASSET_DIR="$assets" "$python_bin" - "$response" <<'PYTHON'
import json
import os
import sys
from pathlib import Path

release = json.load(open(sys.argv[1], encoding="utf-8"))
tag = os.environ["CI_COMMIT_TAG"]
names = sorted(link.get("name") for link in release.get("assets", {}).get("links", []))
expected = sorted(path.name for path in Path(os.environ["ASSET_DIR"]).iterdir() if path.is_file())
if release.get("tag_name") != tag or release.get("name") != f"Codex Responses Proxy {tag}" or names != expected:
    raise SystemExit("existing GitLab release does not match immutable release identity")
PYTHON
    echo "GitLab provider-native release already matches: $CI_COMMIT_TAG"
    ;;
  *) cat "$response" >&2 2>/dev/null || true; echo "GitLab release publication failed with HTTP ${status:-transport-error}" >&2; exit 1 ;;
esac
