#!/bin/sh
# Exercise provider-specific history projection without a network connection.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
script="$root/scripts/project-github-forge.sh"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/codex-dmx-proxy-github-projection.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

source="$tmp/source"
remote="$tmp/github.git"
bootstrap="$tmp/bootstrap"
home="$tmp/home"
global_config="$tmp/global.gitconfig"
key="$tmp/signing"
mock_ssh="$tmp/mock-ssh"
mkdir -p "$home" "$tmp/allowed"
: > "$global_config"
ssh-keygen -q -t ed25519 -N '' -f "$key"
public=$(awk '{print $1" "$2}' "$key.pub")
printf 'heng.yang.ds@hotmail.com namespaces="git" %s\n' "$public" > "$tmp/allowed/gitlab"
printf 'hengyang.2003@tsinghua.org.cn namespaces="git" %s\n' "$public" > "$tmp/allowed/github"

cat > "$mock_ssh" <<'EOF'
#!/bin/sh
case "$*" in
  *git-upload-pack*) exec git-upload-pack "${DMX_TEST_GITHUB_REMOTE:?}" ;;
  *git-receive-pack*) exec git-receive-pack "${DMX_TEST_GITHUB_REMOTE:?}" ;;
esac
exit 0
EOF
chmod +x "$mock_ssh"

export HOME="$home"
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL="$global_config"
git config --file "$global_config" url."https://github.com.invalid/".insteadOf git@github.com:

git init -q --bare "$remote"
git init -q -b main "$source"
git -C "$source" config user.name 'Yang HENG'
git -C "$source" config user.email 'heng.yang.ds@hotmail.com'
git -C "$source" config user.useConfigOnly true
mkdir -p "$source/packaging/release" "$source/scripts"
cp "$tmp/allowed/gitlab" "$source/packaging/release/gitlab-allowed-signers"
cp "$tmp/allowed/github" "$source/packaging/release/github-allowed-signers"
cp "$root/scripts/check-release-tag-signature.sh" "$source/scripts/"
chmod +x "$source/scripts/check-release-tag-signature.sh"
printf 'first\n' > "$source/README.md"
git -C "$source" add .
git -C "$source" commit -qm 'first canonical source commit'
git -C "$source" -c gpg.format=ssh -c user.signingkey="$key" tag -s -a v1.0.0 -m 'GitLab release identity'
canonical_tag=$(git -C "$source" rev-parse refs/tags/v1.0.0)

git clone -q --no-local "file://$source" "$bootstrap"
git -C "$bootstrap" tag -d v1.0.0 >/dev/null
FILTER_BRANCH_SQUELCH_WARNING=1 git -C "$bootstrap" filter-branch -f --env-filter '
  GIT_AUTHOR_NAME="HengYang"
  GIT_AUTHOR_EMAIL="hengyang.2003@tsinghua.org.cn"
  GIT_COMMITTER_NAME="HengYang"
  GIT_COMMITTER_EMAIL="hengyang.2003@tsinghua.org.cn"
' -- main >/dev/null 2>&1
git -C "$bootstrap" for-each-ref --format='%(refname)' refs/original/ | while IFS= read -r ref; do
  git -C "$bootstrap" update-ref -d "$ref"
done
git -C "$bootstrap" -c user.name=HengYang -c user.email=hengyang.2003@tsinghua.org.cn \
  -c gpg.format=ssh -c user.signingkey="$key" tag -s -a v1.0.0 -m 'GitHub release identity'
git -C "$bootstrap" remote set-url origin "file://$remote"
git -C "$bootstrap" -c core.hooksPath=/dev/null push -q origin main refs/tags/v1.0.0
remote_tag_before=$(git -C "$remote" rev-parse refs/tags/v1.0.0)

printf 'second\n' >> "$source/README.md"
git -C "$source" add README.md
git -C "$source" commit -qm 'second canonical source commit'
source_head_before=$(git -C "$source" rev-parse HEAD)
source_refs_before=$(git -C "$source" for-each-ref --format='%(refname) %(objectname)' | LC_ALL=C sort)
git -C "$source" remote add github git@github.com:test/codex-dmx-proxy.git

(
  cd "$source"
  DMX_GITHUB_ALLOWED_SIGNERS="$tmp/allowed/github" \
    DMX_GITLAB_ALLOWED_SIGNERS="$tmp/allowed/gitlab" \
    DMX_TEST_GITHUB_REMOTE="$remote" \
    GIT_SSH_COMMAND="$mock_ssh" \
    DMX_GITHUB_REMOTE=github \
    sh "$script" --branch main
) >/dev/null

[ "$(git -C "$source" rev-parse HEAD)" = "$source_head_before" ] || { echo 'projection rewrote canonical HEAD' >&2; exit 1; }
[ "$(git -C "$source" for-each-ref --format='%(refname) %(objectname)' | LC_ALL=C sort)" = "$source_refs_before" ] || { echo 'projection rewrote canonical refs' >&2; exit 1; }
[ "$(git -C "$source" rev-parse refs/tags/v1.0.0)" = "$canonical_tag" ] || { echo 'projection rewrote canonical GitLab tag' >&2; exit 1; }
[ "$(git -C "$remote" rev-parse refs/tags/v1.0.0)" = "$remote_tag_before" ] || { echo 'projection rewrote GitHub tag' >&2; exit 1; }
[ "$(git -C "$remote" rev-parse refs/heads/main^{tree})" = "$(git -C "$source" rev-parse HEAD^{tree})" ] || { echo 'projected GitHub tree differs from canonical source' >&2; exit 1; }
if git -C "$remote" log main --format='%ae%n%ce' | grep -Fv -x 'hengyang.2003@tsinghua.org.cn' | grep -q .; then
  echo 'GitHub projection retains a non-GitHub identity' >&2
  exit 1
fi

echo 'GitHub provider projection isolation contract: OK'
