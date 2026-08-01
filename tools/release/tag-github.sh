#!/bin/sh
# Create one immutable GitHub-native signed tag for an exact GitLab release tag.
set -eu

tag=${1:?usage: tag-github.sh <v<semver>>}
github_remote=${CODEX_RESPONSES_PROXY_GITHUB_REMOTE:-github}
release_python=${CODEX_RESPONSES_PROXY_RELEASE_PYTHON:-python3}

case "$tag" in v[0-9]*.[0-9]*.[0-9]*) ;; *) echo "release tag must be v<semver>: $tag" >&2; exit 2 ;; esac
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "run inside a Git worktree" >&2; exit 2; }
git diff --quiet && git diff --cached --quiet || { echo "refusing GitHub tag with a dirty canonical checkout" >&2; exit 2; }

root=$(git rev-parse --show-toplevel)
. "$root/tools/forge/context.sh"
load_publication_context github
[ -f "${CODEX_RESPONSES_PROXY_GITHUB_ALLOWED_SIGNERS:-}" ] || {
  echo "GitHub tag trust must be supplied with CODEX_RESPONSES_PROXY_GITHUB_ALLOWED_SIGNERS" >&2
  exit 2
}
[ -f "${CODEX_RESPONSES_PROXY_GITLAB_ALLOWED_SIGNERS:-}" ] || {
  echo "GitLab tag trust must be supplied with CODEX_RESPONSES_PROXY_GITLAB_ALLOWED_SIGNERS" >&2
  exit 2
}
test "$(git rev-parse --abbrev-ref HEAD)" = main || { echo "GitHub release tag must be created from canonical main" >&2; exit 2; }
canonical_head=$(git rev-parse 'HEAD^{commit}')
canonical_tag=$(git rev-parse --verify "refs/tags/$tag")
canonical_tag_commit=$(git rev-parse "refs/tags/$tag^{commit}")
[ "$canonical_tag_commit" = "$canonical_head" ] || { echo "GitLab release tag $tag does not bind canonical HEAD" >&2; exit 1; }
CODEX_RESPONSES_PROXY_RELEASE_ALLOWED_SIGNERS="$CODEX_RESPONSES_PROXY_GITLAB_ALLOWED_SIGNERS" \
  "$root/tools/forge/check-tag-signature.sh" "$root" "$tag" gitlab >/dev/null
"$release_python" "$root/tools/release/metadata.py" --provider gitlab --tag "$tag" >/dev/null
canonical_tree=$(git rev-parse "$canonical_tag_commit^{tree}")
github_url=$(git config --local --get "remote.$github_remote.url" 2>/dev/null) || { echo "GitHub remote is not configured: $github_remote" >&2; exit 2; }

workspace=$(mktemp -d "${TMPDIR:-/tmp}/codex-responses-proxy-github-tag.XXXXXX")
cleanup() { rm -rf "$workspace"; }
trap cleanup EXIT HUP INT TERM
projection="$workspace/repository"
select_agent_signing_key "$workspace/signing-key.pub"
git_transport() { GIT_CONFIG_GLOBAL=/dev/null git "$@"; }

git_transport clone --quiet --no-tags "$github_url" "$projection"
git_transport -C "$projection" fetch --quiet --prune --prune-tags origin
git_transport -C "$projection" fetch --quiet --force --prune --prune-tags origin \
  '+refs/tags/*:refs/tags/*'
if git -C "$projection" show-ref --verify --quiet "refs/tags/$tag"; then
  echo "GitHub tag already exists: $tag" >&2
  exit 1
fi
target=$(git -C "$projection" rev-parse 'refs/remotes/origin/main^{commit}')
[ "$(git -C "$projection" rev-parse "$target^{tree}")" = "$canonical_tree" ] || {
  echo "GitHub main tip tree differs from the canonical release tree for $tag" >&2
  exit 1
}
git -C "$projection" -c user.name="$publication_name" -c user.email="$publication_email" -c user.useConfigOnly=true \
  -c gpg.format=ssh -c gpg.ssh.program="$publication_signing_program" -c user.signingkey="$publication_signing_key" \
  tag -s -a "$tag" "$target" -m "Codex Responses Proxy $tag"
"$release_python" "$projection/tools/release/metadata.py" --provider github --tag "$tag" >/dev/null
CODEX_RESPONSES_PROXY_RELEASE_ALLOWED_SIGNERS="$CODEX_RESPONSES_PROXY_GITHUB_ALLOWED_SIGNERS" \
  "$projection/tools/forge/check-tag-signature.sh" "$projection" "$tag" github >/dev/null
git_transport -C "$projection" push --quiet origin "refs/tags/$tag:refs/tags/$tag"
printf 'GitHub provider-native release tag created: %s (GitLab object %s)\n' "$tag" "$canonical_tag"
