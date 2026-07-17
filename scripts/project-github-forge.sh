#!/bin/sh
# Project one canonical GitLab branch into a GitHub identity history. Only a
# newly created isolated clone is rewritten; provider-native tags are immutable.
set -eu

usage() {
  cat >&2 <<'USAGE'
usage: project-github-forge.sh [--branch <name>] [--github-remote <name>]

Projects a clean canonical branch into the GitHub peer with the GitHub commit
identity. The branch update is leased. Existing same-named release tags must
verify against both provider trust anchors and identify equal source trees; no
tag is copied, regenerated, or overwritten by this command.
USAGE
  exit 2
}

branch=main
github_remote=${DMX_GITHUB_REMOTE:-github}
github_name=${DMX_GITHUB_AUTHOR_NAME:-HengYang}
github_email=${DMX_GITHUB_AUTHOR_EMAIL:-hengyang.2003@tsinghua.org.cn}
github_allowed_signers=${DMX_GITHUB_ALLOWED_SIGNERS:-}
gitlab_allowed_signers=${DMX_GITLAB_ALLOWED_SIGNERS:-}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --branch) branch=${2:?missing branch name}; shift ;;
    --github-remote) github_remote=${2:?missing GitHub remote}; shift ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
  shift
done

case "$branch" in ''|*' '*|*..*|*'~'*|*'^'*|*':'*|*'?'*|*'['*|*'\'*) echo "invalid branch name: $branch" >&2; exit 2 ;; esac
case "$github_name" in HengYang) ;; *) echo "GitHub author name must be HengYang" >&2; exit 2 ;; esac
case "$github_email" in hengyang.2003@tsinghua.org.cn) ;; *) echo "GitHub identity must be hengyang.2003@tsinghua.org.cn" >&2; exit 2 ;; esac

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "run inside a Git worktree" >&2; exit 2; }
git diff --quiet && git diff --cached --quiet || { echo "refusing GitHub projection with a dirty canonical checkout" >&2; exit 2; }

root=$(git rev-parse --show-toplevel)
canonical_common=$(git rev-parse --path-format=absolute --git-common-dir)
canonical=$(git rev-parse "refs/heads/$branch")
canonical_tree=$(git rev-parse "$canonical^{tree}")
github_allowed_signers=${github_allowed_signers:-$root/packaging/release/github-allowed-signers}
gitlab_allowed_signers=${gitlab_allowed_signers:-$root/packaging/release/gitlab-allowed-signers}
[ -f "$github_allowed_signers" ] || { echo "GitHub release trust anchor is missing: $github_allowed_signers" >&2; exit 1; }
[ -f "$gitlab_allowed_signers" ] || { echo "GitLab release trust anchor is missing: $gitlab_allowed_signers" >&2; exit 1; }

# Preserve the exact configured endpoint. `git remote get-url` expands global
# `insteadOf` rules, which may silently exchange the selected transport.
github_url=$(git config --local --get "remote.$github_remote.url" 2>/dev/null) || { echo "GitHub remote is not configured: $github_remote" >&2; exit 2; }
case "$github_url" in *github.com*|file://*) ;; *) echo "$github_remote is not a GitHub remote" >&2; exit 2 ;; esac

workspace=$(mktemp -d "${TMPDIR:-/tmp}/codex-dmx-proxy-github-projection.XXXXXX")
cleanup() { rm -rf "$workspace"; }
trap cleanup EXIT HUP INT TERM
projection="$workspace/repository"

git_transport() { GIT_CONFIG_GLOBAL=/dev/null git "$@"; }

git clone --quiet --no-local "file://$root" "$projection"
projection_common=$(git -C "$projection" rev-parse --path-format=absolute --git-common-dir)
[ "$projection_common" != "$canonical_common" ] || { echo "projection clone shares canonical Git common directory" >&2; exit 1; }
[ ! -e "$projection_common/objects/info/alternates" ] || { echo "projection clone has object alternates" >&2; exit 1; }
git -C "$projection" remote remove origin 2>/dev/null || true
git -C "$projection" for-each-ref --format='delete %(refname)' refs/heads refs/tags | git -C "$projection" update-ref --stdin
git -C "$projection" branch --force "$branch" "$canonical"
git -C "$projection" checkout --quiet "$branch"
FILTER_BRANCH_SQUELCH_WARNING=1 git -C "$projection" filter-branch -f \
  --env-filter '
    GIT_AUTHOR_NAME="HengYang"
    GIT_AUTHOR_EMAIL="hengyang.2003@tsinghua.org.cn"
    GIT_COMMITTER_NAME="HengYang"
    GIT_COMMITTER_EMAIL="hengyang.2003@tsinghua.org.cn"
  ' -- "$branch" >/dev/null 2>&1
git -C "$projection" for-each-ref --format='%(refname)' refs/original/ | while IFS= read -r ref; do
  git -C "$projection" update-ref -d "$ref"
done

projected=$(git -C "$projection" rev-parse "refs/heads/$branch")
[ "$(git -C "$projection" rev-parse "$projected^{tree}")" = "$canonical_tree" ] || { echo "projected GitHub branch tree differs from canonical branch" >&2; exit 1; }
if git -C "$projection" log "$projected" --format='%ae%n%ce' | grep -Fv -x "$github_email" | grep -q .; then
  echo "projected GitHub history retains a non-GitHub identity" >&2
  exit 1
fi

git -C "$projection" remote add github "$github_url"
remote_tip=$(git_transport -C "$projection" ls-remote --heads github "refs/heads/$branch" | awk 'NR==1 {print $1}')
if [ -n "$remote_tip" ]; then
  git_transport -C "$projection" fetch --quiet --no-tags github "refs/heads/$branch:refs/remotes/github/$branch"
  remote_tree=$(git -C "$projection" rev-parse "refs/remotes/github/$branch^{tree}")
  if ! git -C "$projection" log "$canonical" --format='%T' | grep -F -x "$remote_tree" >/dev/null; then
    echo "GitHub branch tree diverges from canonical history; resolve manually" >&2
    exit 1
  fi
fi

# Existing equal-name tags are independent provenance objects. Only validate
# pairs that already exist; historical GitLab tags that predate the GitHub peer
# remain historical evidence rather than a force-push invitation.
remote_tags="$workspace/remote-tags"
git_transport -C "$projection" ls-remote --tags github 'v[0-9]*' > "$remote_tags"
for tag in $(git -C "$root" tag --merged "$canonical" --list 'v[0-9]*'); do
  remote_tag=$(awk -v "needle=refs/tags/$tag" '$2 == needle {print $1; exit}' "$remote_tags")
  [ -n "$remote_tag" ] || continue
  "$root/scripts/check-release-tag-signature.sh" "$root" "$tag" gitlab >/dev/null
  git_transport -C "$projection" fetch --quiet --no-tags github "refs/tags/$tag:refs/tags/github/$tag"
  DMX_RELEASE_ALLOWED_SIGNERS="$github_allowed_signers" \
    "$root/scripts/check-release-tag-signature.sh" "$projection" "github/$tag" github >/dev/null
  [ "$(git -C "$root" rev-parse "$tag^{}^{tree}")" = "$(git -C "$projection" rev-parse "github/$tag^{}^{tree}")" ] || {
    echo "GitHub release tag tree differs from canonical $tag" >&2
    exit 1
  }
done

lease="refs/heads/$branch:${remote_tip:-0000000000000000000000000000000000000000}"
git_transport -C "$projection" -c user.name="$github_name" -c user.email="$github_email" -c user.useConfigOnly=true \
  push --force-with-lease="$lease" github "refs/heads/$branch:refs/heads/$branch"
printf 'GitHub provider projection synchronized: %s\n' "$projected"
