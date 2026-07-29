#!/bin/sh
# Normalize one source branch into a fully signed GitLab provider history.
set -eu

source_ref=${DMX_SOURCE_REF:-HEAD}
gitlab_remote=${DMX_GITLAB_REMOTE:-origin}
gitlab_name=${DMX_GITLAB_AUTHOR_NAME:-Yang HENG}
gitlab_email=${DMX_GITLAB_AUTHOR_EMAIL:-heng.yang.ds@hotmail.com}
signing_key=${DMX_GITLAB_SIGNING_KEY:-$HOME/.ssh/id_aigw_gitlab_signing_20260729.pub}
ssh_signing_program=${DMX_GITLAB_SSH_SIGNING_PROGRAM:-${GPG_SSH_PROGRAM:-}}

case "$gitlab_name:$gitlab_email" in 'Yang HENG:heng.yang.ds@hotmail.com') ;; *) echo "invalid GitLab history identity" >&2; exit 2 ;; esac
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "run inside a Git worktree" >&2; exit 2; }
git diff --quiet && git diff --cached --quiet || { echo "refusing GitLab projection with a dirty source checkout" >&2; exit 2; }

root=$(git rev-parse --show-toplevel)
source=$(git rev-parse "$source_ref")
source_tree=$(git rev-parse "$source^{tree}")
allowed_signers="$root/packaging/release/gitlab-allowed-signers"
gitlab_url=$(git config --local --get "remote.$gitlab_remote.url" 2>/dev/null) || { echo "GitLab remote is not configured: $gitlab_remote" >&2; exit 2; }
case "$gitlab_url" in *192.168.64.101*|file://*) ;; *) echo "$gitlab_remote is not a GitLab remote" >&2; exit 2 ;; esac
if [ -z "$ssh_signing_program" ]; then
  ssh_signing_program=$(git config --get gpg.ssh.program 2>/dev/null || true)
fi
[ -x "$ssh_signing_program" ] || { echo "GitLab SSH signing program is unavailable: $ssh_signing_program" >&2; exit 2; }
[ -f "$signing_key" ] || { echo "GitLab signing key is unavailable: $signing_key" >&2; exit 2; }
[ -f "$allowed_signers" ] || { echo "GitLab trust anchor is unavailable: $allowed_signers" >&2; exit 2; }

workspace=$(mktemp -d "${TMPDIR:-/tmp}/codex-dmx-proxy-gitlab-projection.XXXXXX")
cleanup() { rm -rf "$workspace"; }
trap cleanup EXIT HUP INT TERM
projection="$workspace/repository"

git clone --quiet --no-local "file://$root" "$projection"
git -C "$projection" remote remove origin 2>/dev/null || true
git -C "$projection" for-each-ref --format='delete %(refname)' refs/heads refs/tags | git -C "$projection" update-ref --stdin
git -C "$projection" update-ref refs/heads/source "$source"
python3 "$root/scripts/rewrite-provider-history.py" \
  --repository "$projection" \
  --source-ref refs/heads/source \
  --target-ref refs/heads/main \
  --name "$gitlab_name" \
  --email "$gitlab_email" \
  --signing-key "$signing_key" \
  --signing-program "$ssh_signing_program" \
  --allowed-signers "$allowed_signers" >/dev/null
projected=$(git -C "$projection" rev-parse refs/heads/main)
[ "$(git -C "$projection" rev-parse "$projected^{tree}")" = "$source_tree" ] || { echo "GitLab projection changed the source tree" >&2; exit 1; }

git -C "$projection" remote add gitlab "$gitlab_url"
remote_tip=$(GIT_CONFIG_GLOBAL=/dev/null git -C "$projection" ls-remote --heads gitlab refs/heads/main | awk 'NR==1 {print $1}')
if [ -n "$remote_tip" ]; then
  GIT_CONFIG_GLOBAL=/dev/null git -C "$projection" fetch --quiet --no-tags gitlab refs/heads/main:refs/remotes/gitlab/main
  remote_tree=$(git -C "$projection" rev-parse refs/remotes/gitlab/main^{tree})
  if ! git -C "$projection" log refs/heads/source --format='%T' | grep -F -x "$remote_tree" >/dev/null; then
    echo "GitLab branch tree diverges from source history; resolve manually" >&2
    exit 1
  fi
fi
lease="refs/heads/main:${remote_tip:-0000000000000000000000000000000000000000}"
GIT_CONFIG_GLOBAL=/dev/null git -C "$projection" push --force-with-lease="$lease" gitlab refs/heads/main:refs/heads/main
printf 'GitLab provider history synchronized: %s\n' "$projected"
