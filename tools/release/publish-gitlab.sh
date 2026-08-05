#!/bin/sh
# Mirror one verified GitHub release asset set into the provider-native GitLab release.
set -eu

: "${CI_API_V4_URL:?CI_API_V4_URL is required}"
: "${CI_PROJECT_ID:?CI_PROJECT_ID is required}"
: "${CI_COMMIT_TAG:?CI_COMMIT_TAG is required}"
: "${CI_JOB_TOKEN:?CI_JOB_TOKEN is required}"
: "${CODEX_RESPONSES_PROXY_GITHUB_REPOSITORY:?GitHub owner/repository is required}"
: "${CODEX_RESPONSES_PROXY_RELEASE_ASSET_TRUST:?release asset trust is required}"

case "$CI_API_V4_URL" in http://*|https://*) ;; *) echo "CI_API_V4_URL must be an HTTP(S) URL" >&2; exit 2 ;; esac
case "$CI_PROJECT_ID" in *[!0-9]*|'') echo "CI_PROJECT_ID must be numeric" >&2; exit 2 ;; esac
case "$CI_COMMIT_TAG" in v[0-9]*.[0-9]*.[0-9]*) ;; *) echo "CI_COMMIT_TAG must be a v<semver> tag" >&2; exit 2 ;; esac
case "$CODEX_RESPONSES_PROXY_GITHUB_REPOSITORY" in */*) ;; *) echo "GitHub repository must be owner/repository" >&2; exit 2 ;; esac

python_bin=${PYTHON:-$(command -v python3 || true)}
[ -n "$python_bin" ] || { echo "python3 is required for GitLab release publication" >&2; exit 2; }
command -v ssh-keygen >/dev/null 2>&1 || { echo "ssh-keygen is required" >&2; exit 2; }

work=$(mktemp -d "${TMPDIR:-/tmp}/codex-responses-proxy-gitlab-release.XXXXXX")
assets="$work/assets"
downloaded="$work/downloaded"
payload="$work/release.json"
response="$work/response.json"
anchor="$work/release-asset-trust"
mkdir -p "$assets" "$downloaded"
cleanup() { rm -rf "$work"; }
trap cleanup EXIT HUP INT TERM
printf '%s\n' "$CODEX_RESPONSES_PROXY_RELEASE_ASSET_TRUST" > "$anchor"
chmod 600 "$anchor"

github_api=${CODEX_RESPONSES_PROXY_GITHUB_API_URL:-https://api.github.com}
case "$github_api" in http://*|https://*) ;; *) echo "GitHub API URL must be HTTP(S)" >&2; exit 2 ;; esac
wait_seconds=${CODEX_RESPONSES_PROXY_RELEASE_WAIT_SECONDS:-900}
poll_seconds=${CODEX_RESPONSES_PROXY_RELEASE_POLL_SECONDS:-10}
case "$wait_seconds:$poll_seconds" in *[!0-9:]*|:*|*:) echo "release wait settings must be integers" >&2; exit 2 ;; esac
deadline=$(( $(date +%s) + wait_seconds ))
release_url="$github_api/repos/$CODEX_RESPONSES_PROXY_GITHUB_REPOSITORY/releases/tags/$CI_COMMIT_TAG"

while :; do
  status=$(curl --silent --show-error --location --output "$response" --write-out '%{http_code}' \
    --header 'Accept: application/vnd.github+json' "$release_url" || true)
  if [ "$status" = 200 ]; then
    if RELEASE_JSON="$response" ASSET_DIR="$assets" VERSION="${CI_COMMIT_TAG#v}" \
      "$python_bin" - <<'PYTHON'
import json
import os
from pathlib import Path

from tools.release import product_assets

record = json.loads(Path(os.environ["RELEASE_JSON"]).read_text(encoding="utf-8"))
expected = product_assets.release_asset_names(
    os.environ["VERSION"], product_assets.RELEASE_PLATFORMS
)
assets = record.get("assets")
if not isinstance(assets, list):
    raise SystemExit(1)
urls = {
    item.get("name"): item.get("browser_download_url")
    for item in assets
    if isinstance(item, dict)
}
if set(urls) != expected or any(not isinstance(url, str) for url in urls.values()):
    raise SystemExit(1)
root = Path(os.environ["ASSET_DIR"])
for name, url in sorted(urls.items()):
    (root / f"{name}.url").write_text(url, encoding="utf-8")
PYTHON
    then
      break
    fi
  elif [ "$status" != 404 ]; then
    echo "GitHub release lookup failed with HTTP ${status:-transport-error}" >&2
    exit 1
  fi
  [ "$(date +%s)" -lt "$deadline" ] || {
    echo "GitHub release assets did not become complete before the bounded deadline" >&2
    exit 1
  }
  sleep "$poll_seconds"
done

for url_file in "$assets"/*.url; do
  name=$(basename "$url_file" .url)
  curl --fail --silent --show-error --location --output "$assets/$name" "$(cat "$url_file")"
done
find "$assets" -name '*.url' -delete

principal=$(ssh-keygen -Y find-principals -s "$assets/SHA256SUMS.sig" \
  -f "$anchor" < "$assets/SHA256SUMS")
[ "$principal" = codex-responses-proxy-release ] || {
  echo "release asset signature principal is invalid" >&2
  exit 1
}
ssh-keygen -Y verify -f "$anchor" -I "$principal" \
  -n codex-responses-proxy-release -s "$assets/SHA256SUMS.sig" \
  < "$assets/SHA256SUMS"
"$python_bin" -m tools.release.assemble_assets --verify "$assets"

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
"$python_bin" -m tools.release.assemble_assets --verify "$downloaded"

CI_COMMIT_TAG="$CI_COMMIT_TAG" CODEX_RESPONSES_PROXY_ASSET_BASE="$asset_base" \
  "$python_bin" - "$payload" <<'PYTHON'
import json
import os
import sys

from tools.release import product_assets

tag = os.environ["CI_COMMIT_TAG"]
base = os.environ["CODEX_RESPONSES_PROXY_ASSET_BASE"]
names = sorted(product_assets.release_asset_names(tag.removeprefix("v"), product_assets.RELEASE_PLATFORMS))
links = [{"name": name, "url": f"{base}/{name}", "link_type": "package"} for name in names]
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump({
        "tag_name": tag,
        "name": f"Codex Responses Proxy {tag}",
        "description": "Provider-native release mirrored from the verified cross-platform asset set.",
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

from tools.release import product_assets

release = json.load(open(sys.argv[1], encoding="utf-8"))
tag = os.environ["CI_COMMIT_TAG"]
names = sorted(link.get("name") for link in release.get("assets", {}).get("links", []))
expected = sorted(product_assets.release_asset_names(tag.removeprefix("v"), product_assets.RELEASE_PLATFORMS))
if release.get("tag_name") != tag or release.get("name") != f"Codex Responses Proxy {tag}" or names != expected:
    raise SystemExit("existing GitLab release does not match immutable release identity")
PYTHON
    echo "GitLab provider-native release already matches: $CI_COMMIT_TAG"
    ;;
  *) cat "$response" >&2 2>/dev/null || true; echo "GitLab release publication failed with HTTP ${status:-transport-error}" >&2; exit 1 ;;
esac
