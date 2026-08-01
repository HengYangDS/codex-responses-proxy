#!/bin/sh
# Create one immutable GitLab-native signed tag using the GitLab trust anchor.
set -eu

tag=${1:?usage: tag-gitlab.sh <v<semver>>}
gitlab_remote=${CODEX_RESPONSES_PROXY_GITLAB_REMOTE:-origin}
release_python=${CODEX_RESPONSES_PROXY_RELEASE_PYTHON:-python3}

case "$tag" in v[0-9]*.[0-9]*.[0-9]*) ;; *) echo "release tag must be v<semver>: $tag" >&2; exit 2 ;; esac
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "run inside a Git worktree" >&2; exit 2; }
git diff --quiet && git diff --cached --quiet || { echo "refusing GitLab tag with a dirty canonical checkout" >&2; exit 2; }

root=$(git rev-parse --show-toplevel)
. "$root/tools/forge/context.sh"
load_publication_context gitlab
[ -f "${CODEX_RESPONSES_PROXY_GITLAB_ALLOWED_SIGNERS:-}" ] || {
  echo "GitLab tag trust must be supplied with CODEX_RESPONSES_PROXY_GITLAB_ALLOWED_SIGNERS" >&2
  exit 2
}
test "$(git rev-parse --abbrev-ref HEAD)" = main || { echo "GitLab release tag must be created from main" >&2; exit 2; }
gitlab_url=$(git config --local --get "remote.$gitlab_remote.url" 2>/dev/null) || { echo "GitLab remote is not configured: $gitlab_remote" >&2; exit 2; }
workspace=$(mktemp -d "${TMPDIR:-/tmp}/codex-responses-proxy-gitlab-tag.XXXXXX")
cleanup() { rm -rf "$workspace"; }
trap cleanup EXIT HUP INT TERM
select_agent_signing_key "$workspace/signing-key.pub"

git ls-remote --exit-code --tags "$gitlab_remote" "refs/tags/$tag" >/dev/null 2>&1 && { echo "GitLab tag already exists: $tag" >&2; exit 1; }
git rev-parse --verify "refs/tags/$tag" >/dev/null 2>&1 && { echo "local tag already exists: $tag" >&2; exit 1; }
"$release_python" "$root/tools/release/metadata.py" --provider gitlab --prepare-release >/dev/null
git -c user.name="$publication_name" -c user.email="$publication_email" -c user.useConfigOnly=true \
  -c gpg.format=ssh -c gpg.ssh.program="$publication_signing_program" -c user.signingkey="$publication_signing_key" \
  tag -s -a "$tag" -m "Codex Responses Proxy $tag"
CODEX_RESPONSES_PROXY_RELEASE_ALLOWED_SIGNERS="$CODEX_RESPONSES_PROXY_GITLAB_ALLOWED_SIGNERS" \
  "$root/tools/forge/check-tag-signature.sh" "$root" "$tag" gitlab >/dev/null
git push --quiet "$gitlab_remote" "refs/tags/$tag:refs/tags/$tag"
printf 'GitLab provider-native release tag created: %s\n' "$tag"
