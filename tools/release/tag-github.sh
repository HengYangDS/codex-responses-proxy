#!/bin/sh
# Create one immutable GitHub-native signed tag from GitHub main.
set -eu

provider=github
tag=${1:?usage: tag-github.sh <v<semver>>}
remote=${CODEX_RESPONSES_PROXY_GITHUB_REMOTE:-github}
allowed_signers=${CODEX_RESPONSES_PROXY_GITHUB_ALLOWED_SIGNERS:-}
release_python=${CODEX_RESPONSES_PROXY_RELEASE_PYTHON:-python3}

case "$tag" in v[0-9]*.[0-9]*.[0-9]*) ;; *) echo "release tag must be v<semver>: $tag" >&2; exit 2 ;; esac
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "run inside a Git worktree" >&2; exit 2; }
git diff --quiet && git diff --cached --quiet || { echo "refusing GitHub tag with a dirty checkout" >&2; exit 2; }

root=$(git rev-parse --show-toplevel)
. "$root/tools/forge/context.sh"
load_publication_context "$provider"
[ -f "$allowed_signers" ] || publication_error \
  "GitHub tag trust must be supplied with CODEX_RESPONSES_PROXY_GITHUB_ALLOWED_SIGNERS"
remote_url=$(git config --local --get "remote.$remote.url" 2>/dev/null) || publication_error \
  "GitHub remote is not configured: $remote"

workspace=$(mktemp -d "${TMPDIR:-/tmp}/codex-responses-proxy-github-tag.XXXXXX")
cleanup() { rm -rf "$workspace"; }
trap cleanup EXIT HUP INT TERM
repository="$workspace/repository"
select_agent_signing_key "$workspace/signing-key.pub"
git_transport() { GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git "$@"; }

git_transport clone --quiet --no-tags "$remote_url" "$repository"
git_transport -C "$repository" fetch --quiet --prune --prune-tags origin
git_transport -C "$repository" fetch --quiet --force --prune --prune-tags origin \
  '+refs/tags/*:refs/tags/*'
if git -C "$repository" show-ref --verify --quiet "refs/tags/$tag"; then
  echo "GitHub tag already exists: $tag" >&2
  exit 1
fi

target=$(git -C "$repository" rev-parse 'refs/remotes/origin/main^{commit}')
git -C "$repository" checkout --quiet --detach "$target"
"$release_python" "$repository/tools/release/metadata.py" \
  --provider github --prepare-release >/dev/null
git -C "$repository" -c user.name="$publication_name" -c user.email="$publication_email" \
  -c user.useConfigOnly=true -c gpg.format=ssh \
  -c gpg.ssh.program="$publication_signing_program" \
  -c user.signingkey="$publication_signing_key" \
  tag -s -a "$tag" "$target" -m "Codex Responses Proxy $tag"
"$release_python" "$repository/tools/release/metadata.py" --provider github --tag "$tag" >/dev/null
CODEX_RESPONSES_PROXY_RELEASE_ALLOWED_SIGNERS="$allowed_signers" \
  "$repository/tools/forge/check-tag-signature.sh" "$repository" "$tag" github >/dev/null
git_transport -C "$repository" push --quiet origin "refs/tags/$tag:refs/tags/$tag"
printf 'GitHub provider-native release tag created: %s\n' "$tag"
