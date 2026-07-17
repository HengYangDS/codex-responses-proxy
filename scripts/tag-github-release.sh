#!/bin/sh
# Create one immutable GitHub-native signed tag for a signed GitLab release tag.
set -eu

tag=${1:?usage: tag-github-release.sh <v<semver>>}
github_remote=${DMX_GITHUB_REMOTE:-github}
github_name=${DMX_GITHUB_AUTHOR_NAME:-HengYang}
github_email=${DMX_GITHUB_AUTHOR_EMAIL:-hengyang.2003@tsinghua.org.cn}
signing_key=${DMX_GITHUB_SIGNING_KEY:-$HOME/.ssh/id_ed25519_signing_yheng_20260711.pub}
ssh_signing_program=${DMX_GITHUB_SSH_SIGNING_PROGRAM:-${GPG_SSH_PROGRAM:-}}

case "$tag" in v[0-9]*.[0-9]*.[0-9]*) ;; *) echo "release tag must be v<semver>: $tag" >&2; exit 2 ;; esac
case "$github_name:$github_email" in HengYang:hengyang.2003@tsinghua.org.cn) ;; *) echo "invalid GitHub release identity" >&2; exit 2 ;; esac

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "run inside a Git worktree" >&2; exit 2; }
git diff --quiet && git diff --cached --quiet || { echo "refusing GitHub tag with a dirty canonical checkout" >&2; exit 2; }

root=$(git rev-parse --show-toplevel)
canonical_tag=$(git rev-parse --verify "refs/tags/$tag")
"$root/scripts/check-release-tag-signature.sh" "$root" "$tag" gitlab >/dev/null
canonical_tree=$(git rev-parse "$tag^{}^{tree}")
if [ -z "$ssh_signing_program" ]; then
  ssh_signing_program=$(git config --get gpg.ssh.program 2>/dev/null || true)
fi
[ -n "$ssh_signing_program" ] || { echo "GitHub SSH signing program is not configured" >&2; exit 2; }
[ -x "$ssh_signing_program" ] || { echo "GitHub SSH signing program is not executable: $ssh_signing_program" >&2; exit 2; }
github_url=$(git config --local --get "remote.$github_remote.url" 2>/dev/null) || { echo "GitHub remote is not configured: $github_remote" >&2; exit 2; }
case "$github_url" in *github.com*|file://*) ;; *) echo "$github_remote is not a GitHub remote" >&2; exit 2 ;; esac

workspace=$(mktemp -d "${TMPDIR:-/tmp}/codex-dmx-proxy-github-tag.XXXXXX")
cleanup() { rm -rf "$workspace"; }
trap cleanup EXIT HUP INT TERM
projection="$workspace/repository"
git_transport() { GIT_CONFIG_GLOBAL=/dev/null git "$@"; }

git_transport clone --quiet --no-tags "$github_url" "$projection"
git -C "$projection" fetch --quiet --no-tags origin refs/heads/main:refs/remotes/origin/main
target=$(git -C "$projection" log refs/remotes/origin/main --format='%H %T' | awk -v tree="$canonical_tree" '$2 == tree {print $1; exit}')
[ -n "$target" ] || { echo "GitHub main does not contain the canonical release tree for $tag" >&2; exit 1; }
if git_transport -C "$projection" ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null 2>&1; then
  echo "GitHub tag already exists: $tag" >&2
  exit 1
fi
git -C "$projection" -c user.name="$github_name" -c user.email="$github_email" -c user.useConfigOnly=true \
  -c gpg.format=ssh -c gpg.ssh.program="$ssh_signing_program" -c user.signingkey="$signing_key" \
  tag -s -a "$tag" "$target" -m "Codex DMX Proxy $tag"
DMX_RELEASE_ALLOWED_SIGNERS="$root/packaging/release/github-allowed-signers" \
  "$root/scripts/check-release-tag-signature.sh" "$projection" "$tag" github >/dev/null
git_transport -C "$projection" push origin "refs/tags/$tag:refs/tags/$tag"
printf 'GitHub provider-native release tag created: %s (%s)\n' "$tag" "$canonical_tag"
