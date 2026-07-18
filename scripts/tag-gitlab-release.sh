#!/bin/sh
# Create one immutable GitLab-native signed tag using the GitLab trust anchor.
set -eu

tag=${1:?usage: tag-gitlab-release.sh <v<semver>>}
gitlab_remote=${DMX_GITLAB_REMOTE:-origin}
gitlab_name=${DMX_GITLAB_AUTHOR_NAME:-Yang HENG}
gitlab_email=${DMX_GITLAB_AUTHOR_EMAIL:-heng.yang.ds@hotmail.com}
signing_key=${DMX_GITLAB_SIGNING_KEY:-$HOME/.ssh/id_ed25519_signing_yheng_20260711.pub}
ssh_signing_program=${DMX_GITLAB_SSH_SIGNING_PROGRAM:-${GPG_SSH_PROGRAM:-}}

case "$tag" in v[0-9]*.[0-9]*.[0-9]*) ;; *) echo "release tag must be v<semver>: $tag" >&2; exit 2 ;; esac
case "$gitlab_name:$gitlab_email" in 'Yang HENG:heng.yang.ds@hotmail.com') ;; *) echo "invalid GitLab release identity" >&2; exit 2 ;; esac

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "run inside a Git worktree" >&2; exit 2; }
git diff --quiet && git diff --cached --quiet || { echo "refusing GitLab tag with a dirty canonical checkout" >&2; exit 2; }

root=$(git rev-parse --show-toplevel)
test "$(git rev-parse --abbrev-ref HEAD)" = main || { echo "GitLab release tag must be created from main" >&2; exit 2; }
gitlab_url=$(git config --local --get "remote.$gitlab_remote.url" 2>/dev/null) || { echo "GitLab remote is not configured: $gitlab_remote" >&2; exit 2; }
case "$gitlab_url" in *192.168.64.101*|file://*) ;; *) echo "$gitlab_remote is not a GitLab remote" >&2; exit 2 ;; esac
if [ -z "$ssh_signing_program" ]; then
  ssh_signing_program=$(git config --get gpg.ssh.program 2>/dev/null || true)
fi
[ -n "$ssh_signing_program" ] || { echo "GitLab SSH signing program is not configured" >&2; exit 2; }
[ -x "$ssh_signing_program" ] || { echo "GitLab SSH signing program is not executable: $ssh_signing_program" >&2; exit 2; }
[ -f "$signing_key" ] || { echo "GitLab signing key is unavailable: $signing_key" >&2; exit 2; }

git ls-remote --exit-code --tags "$gitlab_remote" "refs/tags/$tag" >/dev/null 2>&1 && { echo "GitLab tag already exists: $tag" >&2; exit 1; }
git rev-parse --verify "refs/tags/$tag" >/dev/null 2>&1 && { echo "local tag already exists: $tag" >&2; exit 1; }
git -c user.name="$gitlab_name" -c user.email="$gitlab_email" -c user.useConfigOnly=true \
  -c gpg.format=ssh -c gpg.ssh.program="$ssh_signing_program" -c user.signingkey="$signing_key" \
  tag -s -a "$tag" -m "Codex DMX Proxy $tag"
"$root/scripts/check-release-tag-signature.sh" "$root" "$tag" gitlab >/dev/null
git push "$gitlab_remote" "refs/tags/$tag:refs/tags/$tag"
printf 'GitLab provider-native release tag created: %s\n' "$tag"
