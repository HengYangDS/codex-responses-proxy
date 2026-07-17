#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
script="$root/scripts/publish-gitlab-release.sh"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/codex-dmx-proxy-gitlab-release.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

mock_curl="$tmp/curl"
log="$tmp/curl.log"
cat > "$mock_curl" <<'EOF'
#!/bin/sh
set -eu
output=
method=GET
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output) output=$2; shift 2 ;;
    --request) method=$2; shift 2 ;;
    --header|--data|--write-out) shift 2 ;;
    --silent|--show-error) shift ;;
    *) url=$1; shift ;;
  esac
done
printf '%s %s\n' "$method" "${url:-}" >> "${DMX_TEST_CURL_LOG:?}"
case "${DMX_TEST_CURL_MODE:?}" in
  create)
    printf '{"tag_name":"v1.0.9","name":"Codex DMX Proxy v1.0.9"}' > "$output"
    printf 201
    ;;
  existing)
    if [ "$method" = POST ]; then
      printf '{}' > "$output"; printf 409
    else
      printf '{"tag_name":"v1.0.9","name":"Codex DMX Proxy v1.0.9"}' > "$output"; printf 200
    fi
    ;;
  mismatch)
    if [ "$method" = POST ]; then
      printf '{}' > "$output"; printf 409
    else
      printf '{"tag_name":"v1.0.9","name":"wrong"}' > "$output"; printf 200
    fi
    ;;
esac
EOF
chmod +x "$mock_curl"

run() {
  mode=$1
  PATH="$tmp:$PATH" DMX_TEST_CURL_LOG="$log" DMX_TEST_CURL_MODE="$mode" \
    CI_API_V4_URL=https://gitlab.example.test/api/v4 CI_PROJECT_ID=453 \
    CI_COMMIT_TAG=v1.0.9 CI_JOB_TOKEN=redacted \
    sh "$script"
}

run create > "$tmp/create.out"
grep -Fx 'GitLab provider-native release created: v1.0.9' "$tmp/create.out" >/dev/null
run existing > "$tmp/existing.out"
grep -Fx 'GitLab provider-native release already matches: v1.0.9' "$tmp/existing.out" >/dev/null
if run mismatch >/dev/null 2>&1; then
  echo 'publisher accepted a mismatched immutable release record' >&2
  exit 1
fi
grep -F 'POST https://gitlab.example.test/api/v4/projects/453/releases' "$log" >/dev/null
grep -F 'GET https://gitlab.example.test/api/v4/projects/453/releases/v1.0.9' "$log" >/dev/null

echo 'GitLab release publication contract: OK'
