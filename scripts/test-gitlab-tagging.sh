#!/bin/sh
# Exercise provider-native GitLab tag creation without a network connection.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
script="$root/scripts/tag-gitlab-release.sh"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/codex-dmx-proxy-gitlab-tagging.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

source="$tmp/source"
remote="$tmp/gitlab.git"
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

cat > "$mock_ssh" <<'EOF'
#!/bin/sh
case "$*" in
  *git-upload-pack*) exec git-upload-pack "${DMX_TEST_GITLAB_REMOTE:?}" ;;
  *git-receive-pack*) exec git-receive-pack "${DMX_TEST_GITLAB_REMOTE:?}" ;;
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
cp "$root/scripts/check-release-tag-signature.sh" "$source/scripts/"
chmod +x "$source/scripts/check-release-tag-signature.sh"
printf 'release source\n' > "$source/README.md"
git -C "$source" add .
git -C "$source" commit -qm 'release source'
git -C "$source" remote add origin git@192.168.64.101:1122/test/codex-dmx-proxy.git

(
  cd "$source"
  DMX_GITLAB_SIGNING_KEY="$key" \
  DMX_TEST_GITLAB_REMOTE="$remote" \
  GIT_SSH_COMMAND="$mock_ssh" \
  sh "$script" v1.0.0
) >/dev/null

grep -F -- '-Y sign' "$signing_log" >/dev/null || {
  echo 'GitLab tag creation bypassed the configured SSH signing program' >&2
  exit 1
}
git -C "$remote" rev-parse --verify refs/tags/v1.0.0 >/dev/null
git -C "$remote" -c gpg.format=ssh -c gpg.ssh.program=ssh-keygen \
  -c gpg.ssh.allowedSignersFile="$tmp/allowed/gitlab" verify-tag v1.0.0 >/dev/null
[ "$(git -C "$remote" rev-parse 'v1.0.0^{}^{tree}')" = "$(git -C "$source" rev-parse HEAD^{tree})" ] || {
  echo 'GitLab release tag tree differs from canonical main' >&2
  exit 1
}

echo 'GitLab provider tag creation contract: OK'
