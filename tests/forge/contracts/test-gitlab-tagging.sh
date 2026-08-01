#!/bin/sh
# Exercise provider-native GitLab tag creation without a network connection.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
script="$root/tools/release/tag-gitlab.sh"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/codex-responses-proxy-gitlab-tagging.XXXXXX")
cleanup() {
  ssh-agent -k >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT HUP INT TERM

source="$tmp/source"
remote="$tmp/gitlab.git"
home="$tmp/home"
global_config="$tmp/global.gitconfig"
key="$tmp/signing"
mock_ssh="$tmp/mock-ssh"
mock_python="$tmp/mock-python3"
metadata_log="$tmp/metadata.log"
mkdir -p "$home" "$tmp/allowed"
: > "$global_config"
ssh-keygen -q -t ed25519 -N '' -f "$key"
public=$(awk '{print $1" "$2}' "$key.pub")
gitlab_email=gitlab-publisher@example.test
printf '%s namespaces="git" %s\n' "$gitlab_email" "$public" > "$tmp/allowed/gitlab"
eval "$(ssh-agent -s)" >/dev/null
ssh-add "$key" >/dev/null 2>&1

cat > "$mock_ssh" <<'EOF'
#!/bin/sh
case "$*" in
  *git-upload-pack*) exec git-upload-pack "${CODEX_RESPONSES_PROXY_TEST_GITLAB_REMOTE:?}" ;;
  *git-receive-pack*) exec git-receive-pack "${CODEX_RESPONSES_PROXY_TEST_GITLAB_REMOTE:?}" ;;
esac
exit 0
EOF
chmod +x "$mock_ssh"

cat > "$mock_python" <<'EOF'
#!/bin/sh
set -eu
printf '%s\n' "$*" >> "${CODEX_RESPONSES_PROXY_TEST_METADATA_LOG:?}"
EOF
chmod +x "$mock_python"

export HOME="$home"
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL="$global_config"
git config --file "$global_config" gpg.ssh.program /nonexistent/personal-signing-wrapper
git init -q --bare "$remote"
git init -q -b main "$source"
git -C "$source" config user.name 'Fixture Release Actor'
git -C "$source" config user.email "$gitlab_email"
git -C "$source" config user.useConfigOnly true
mkdir -p "$source/tools/forge" "$source/tools/release"
context="$tmp/publication-context.toml"
cat > "$context" <<EOF_POLICY
schema-version = 1
[gitlab]
actor-name = "Fixture Release Actor"
actor-email = "$gitlab_email"
active-signing-fingerprint = "$(ssh-keygen -lf "$key.pub" -E sha256 | awk '{print $2}')"
EOF_POLICY
cp "$root/tools/forge/check-tag-signature.sh" "$source/tools/forge/"
cp "$root/tools/forge/context.sh" "$source/tools/forge/"
chmod +x "$source/tools/forge/check-tag-signature.sh" "$source/tools/forge/context.sh"
printf 'release source\n' > "$source/README.md"
git -C "$source" add .
git -C "$source" commit -qm 'release source'
git -C "$source" remote add origin file://$remote

(
  cd "$source"
  CODEX_RESPONSES_PROXY_PUBLICATION_CONTEXT="$context" \
  CODEX_RESPONSES_PROXY_GITLAB_ALLOWED_SIGNERS="$tmp/allowed/gitlab" \
  CODEX_RESPONSES_PROXY_GITLAB_SIGNING_KEY="$key" \
  CODEX_RESPONSES_PROXY_RELEASE_PYTHON="$mock_python" \
  CODEX_RESPONSES_PROXY_TEST_METADATA_LOG="$metadata_log" \
  CODEX_RESPONSES_PROXY_TEST_GITLAB_REMOTE="$remote" \
  GIT_SSH_COMMAND="$mock_ssh" \
  sh "$script" v1.0.0
) >"$tmp/tagger.out" 2>"$tmp/tagger.err"

grep -F -- 'metadata.py --provider gitlab --prepare-release' "$metadata_log" >/dev/null || {
  echo 'GitLab tag creation bypassed the pending-release metadata preflight' >&2
  exit 1
}
git -C "$remote" rev-parse --verify refs/tags/v1.0.0 >/dev/null
git -C "$remote" -c gpg.format=ssh -c gpg.ssh.program=ssh-keygen \
  -c gpg.ssh.allowedSignersFile="$tmp/allowed/gitlab" verify-tag v1.0.0 >/dev/null 2>&1
[ "$(git -C "$remote" rev-parse 'v1.0.0^{}^{tree}')" = "$(git -C "$source" rev-parse HEAD^{tree})" ] || {
  echo 'GitLab release tag tree differs from canonical main' >&2
  exit 1
}

echo 'GitLab provider tag creation contract: OK'
