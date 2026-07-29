#!/bin/sh
# Create one immutable GitHub-native signed tag for an exact GitLab release tag.
set -eu

tag=${1:?usage: tag-github-release.sh <v<semver>>}
github_remote=${DMX_GITHUB_REMOTE:-github}
github_name=${DMX_GITHUB_AUTHOR_NAME:-Yang HENG}
github_email=${DMX_GITHUB_AUTHOR_EMAIL:-hengyang.2003@tsinghua.org.cn}
signing_key=${DMX_GITHUB_SIGNING_KEY:-$HOME/.ssh/id_aigw_github_signing_20260729.pub}
ssh_signing_program=${DMX_GITHUB_SSH_SIGNING_PROGRAM:-${GPG_SSH_PROGRAM:-}}
release_python=${DMX_RELEASE_PYTHON:-python3}

case "$tag" in v[0-9]*.[0-9]*.[0-9]*) ;; *) echo "release tag must be v<semver>: $tag" >&2; exit 2 ;; esac
case "$github_name:$github_email" in 'Yang HENG:hengyang.2003@tsinghua.org.cn') ;; *) echo "invalid GitHub release identity" >&2; exit 2 ;; esac

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "run inside a Git worktree" >&2; exit 2; }
git diff --quiet && git diff --cached --quiet || { echo "refusing GitHub tag with a dirty canonical checkout" >&2; exit 2; }

root=$(git rev-parse --show-toplevel)
test "$(git rev-parse --abbrev-ref HEAD)" = main || { echo "GitHub release tag must be created from canonical main" >&2; exit 2; }
canonical_head=$(git rev-parse 'HEAD^{commit}')
canonical_tag=$(git rev-parse --verify "refs/tags/$tag")
canonical_tag_commit=$(git rev-parse "refs/tags/$tag^{commit}")
[ "$canonical_tag_commit" = "$canonical_head" ] || { echo "GitLab release tag $tag does not bind canonical HEAD" >&2; exit 1; }
"$root/scripts/check-release-tag-signature.sh" "$root" "$tag" gitlab >/dev/null
"$release_python" "$root/scripts/check_release_metadata.py" --provider gitlab --tag "$tag" >/dev/null
canonical_tree=$(git rev-parse "$canonical_tag_commit^{tree}")
if [ -z "$ssh_signing_program" ]; then
  ssh_signing_program=$(git config --get gpg.ssh.program 2>/dev/null || true)
fi
[ -n "$ssh_signing_program" ] || { echo "GitHub SSH signing program is not configured" >&2; exit 2; }
[ -x "$ssh_signing_program" ] || { echo "GitHub SSH signing program is not executable: $ssh_signing_program" >&2; exit 2; }
[ -f "$signing_key" ] || { echo "GitHub signing key is unavailable: $signing_key" >&2; exit 2; }
github_url=$(git config --local --get "remote.$github_remote.url" 2>/dev/null) || { echo "GitHub remote is not configured: $github_remote" >&2; exit 2; }
case "$github_url" in *github.com*|file://*) ;; *) echo "$github_remote is not a GitHub remote" >&2; exit 2 ;; esac

workspace=$(mktemp -d "${TMPDIR:-/tmp}/codex-dmx-proxy-github-tag.XXXXXX")
cleanup() { rm -rf "$workspace"; }
trap cleanup EXIT HUP INT TERM
projection="$workspace/repository"
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
git -C "$projection" -c user.name="$github_name" -c user.email="$github_email" -c user.useConfigOnly=true \
  -c gpg.format=ssh -c gpg.ssh.program="$ssh_signing_program" -c user.signingkey="$signing_key" \
  tag -s -a "$tag" "$target" -m "Codex DMX Proxy $tag"
"$release_python" "$projection/scripts/check_release_metadata.py" --provider github --tag "$tag" >/dev/null
DMX_RELEASE_ALLOWED_SIGNERS="$projection/packaging/release/github-allowed-signers" \
  "$projection/scripts/check-release-tag-signature.sh" "$projection" "$tag" github >/dev/null
git_transport -C "$projection" push origin "refs/tags/$tag:refs/tags/$tag"
printf 'GitHub provider-native release tag created: %s (GitLab object %s)\n' "$tag" "$canonical_tag"
