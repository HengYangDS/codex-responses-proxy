#!/bin/sh
# Exercise creation of a provider-native GitHub tag for a GitLab release tree.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
script="$root/scripts/tag-github-release.sh"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/codex-dmx-proxy-github-tagging.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

source="$tmp/source"
remote="$tmp/github.git"
home="$tmp/home"
global_config="$tmp/global.gitconfig"
key="$tmp/signing"
mock_ssh="$tmp/mock-ssh"
signing_wrapper="$tmp/signing-wrapper"
signing_log="$tmp/signing.log"
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

cat > "$signing_wrapper" <<'EOF'
#!/bin/sh
set -eu
printf '%s\n' "$*" >> "${DMX_TEST_SIGNING_LOG:?}"
exec ssh-keygen "$@"
EOF
chmod +x "$signing_wrapper"

export HOME="$home"
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL="$global_config"
export DMX_TEST_SIGNING_LOG="$signing_log"
git config --file "$global_config" gpg.ssh.program "$signing_wrapper"
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
printf 'release source\n' > "$source/README.md"
git -C "$source" add .
git -C "$source" commit -qm 'release source'
git -C "$source" -c gpg.format=ssh -c user.signingkey="$key" tag -s -a v1.0.0 -m 'GitLab release identity'

projection="$tmp/projection"
git clone -q --no-local "file://$source" "$projection"
git -C "$projection" tag -d v1.0.0 >/dev/null
FILTER_BRANCH_SQUELCH_WARNING=1 git -C "$projection" filter-branch -f --env-filter '
  GIT_AUTHOR_NAME="HengYang"
  GIT_AUTHOR_EMAIL="hengyang.2003@tsinghua.org.cn"
  GIT_COMMITTER_NAME="HengYang"
  GIT_COMMITTER_EMAIL="hengyang.2003@tsinghua.org.cn"
' -- main >/dev/null 2>&1
git -C "$projection" remote set-url origin "file://$remote"
git -C "$projection" push -q origin main

git -C "$source" remote add github git@github.com:test/codex-dmx-proxy.git
(
  cd "$source"
    DMX_GITHUB_ALLOWED_SIGNERS="$tmp/allowed/github" \
    DMX_GITLAB_ALLOWED_SIGNERS="$tmp/allowed/gitlab" \
    DMX_GITHUB_SIGNING_KEY="$key" \
    DMX_TEST_GITHUB_REMOTE="$remote" \
    GIT_SSH_COMMAND="$mock_ssh" \
    DMX_GITHUB_REMOTE=github \
    sh "$script" v1.0.0
) >/dev/null

grep -F -- '-Y sign' "$signing_log" >/dev/null || {
  echo 'GitHub tag creation bypassed the configured SSH signing program' >&2
  exit 1
}
git -C "$remote" rev-parse --verify refs/tags/v1.0.0 >/dev/null
git -C "$remote" -c gpg.format=ssh -c gpg.ssh.program=ssh-keygen \
  -c gpg.ssh.allowedSignersFile="$tmp/allowed/github" verify-tag v1.0.0 >/dev/null
[ "$(git -C "$remote" rev-parse 'v1.0.0^{}^{tree}')" = "$(git -C "$source" rev-parse 'v1.0.0^{}^{tree}')" ] || {
  echo 'GitHub release tag tree differs from GitLab release tag tree' >&2
  exit 1
}

echo 'GitHub provider tag creation contract: OK'
