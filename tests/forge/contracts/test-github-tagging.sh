#!/bin/sh
# Exercise the two-provider GitHub tag sequence without a network connection.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
script="$root/tools/release/tag-github.sh"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/codex-responses-proxy-github-tagging.XXXXXX")
cleanup() {
  ssh-agent -k >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT HUP INT TERM

source="$tmp/source"
remote="$tmp/github.git"
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
gitlab_email=local-builder@example.test
github_email=github-publisher@example.test
printf '%s namespaces="git" %s\n' "$github_email" "$public" > "$tmp/allowed/github"
eval "$(ssh-agent -s)" >/dev/null
ssh-add "$key" >/dev/null 2>&1

cat > "$mock_ssh" <<'EOF_SSH'
#!/bin/sh
case "$*" in
  *git-upload-pack*) exec git-upload-pack "${CODEX_RESPONSES_PROXY_TEST_GITHUB_REMOTE:?}" ;;
  *git-receive-pack*) exec git-receive-pack "${CODEX_RESPONSES_PROXY_TEST_GITHUB_REMOTE:?}" ;;
esac
exit 0
EOF_SSH
chmod +x "$mock_ssh"

cat > "$mock_python" <<'EOF_PYTHON'
#!/bin/sh
set -eu
checker=$1
repo=${checker%/tools/release/metadata.py}
repo=$(CDPATH= cd -- "$repo" && pwd)
canonical=$(git -C "${CODEX_RESPONSES_PROXY_TEST_CANONICAL:?}" rev-parse --show-toplevel)
printf '%s|%s\n' "$repo" "$*" >> "${CODEX_RESPONSES_PROXY_TEST_METADATA_LOG:?}"
case "$*" in
  *'--provider github --prepare-release'*)
    test "$repo" != "$canonical" || {
      echo 'GitHub preparation ran outside the isolated provider checkout' >&2
      exit 90
    }
    ;;
  *'--provider github --tag '*)
    test "$repo" != "$canonical" || {
      echo 'GitHub metadata preflight ran outside the isolated provider checkout' >&2
      exit 91
    }
    git -C "$repo" show-ref --verify --quiet "refs/tags/${CODEX_RESPONSES_PROXY_TEST_TAG:?}" || {
      echo 'GitHub metadata preflight ran before tag creation' >&2
      exit 92
    }
    ;;
  *)
    echo "unexpected release metadata invocation: $*" >&2
    exit 93
    ;;
esac
EOF_PYTHON
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
fingerprint=$(ssh-keygen -lf "$key.pub" -E sha256 | awk '{print $2}')
context="$tmp/publication-context.toml"
cat > "$context" <<EOF_POLICY
schema-version = 1
[gitlab]
actor-name = "Fixture Release Actor"
actor-email = "$gitlab_email"
active-signing-fingerprint = "$fingerprint"

[github]
actor-name = "Fixture Release Actor"
actor-email = "$github_email"
active-signing-fingerprint = "$fingerprint"
EOF_POLICY
cp "$root/tools/forge/check-tag-signature.sh" "$source/tools/forge/"
cp "$root/tools/release/metadata.py" "$source/tools/release/"
cp "$root/tools/forge/context.sh" "$source/tools/forge/"
chmod +x "$source/tools/forge/check-tag-signature.sh" "$source/tools/release/metadata.py" "$source/tools/forge/context.sh"
printf 'release source\n' > "$source/README.md"
git -C "$source" add .
git -C "$source" commit -qm 'release source'
projection="$tmp/projection"
git clone -q --no-local "file://$source" "$projection"
git -C "$projection" remote set-url origin "file://$remote"
git -C "$projection" push -q origin main
git -C "$remote" symbolic-ref HEAD refs/heads/main
git -C "$projection" -c user.name='Fixture Publisher' -c user.email="$github_email" \
  -c user.useConfigOnly=true -c gpg.format=ssh -c gpg.ssh.program=ssh-keygen \
  -c user.signingkey="$key" tag -s -a v0.9.0 -m 'existing GitHub tag'
git -C "$projection" push -q origin refs/tags/v0.9.0:refs/tags/v0.9.0
existing_tag=$(git -C "$remote" rev-parse refs/tags/v0.9.0)

git -C "$source" remote add github file://$remote
run_tag() {
  target_tag=$1
  shift
  (
    cd "$source"
    CODEX_RESPONSES_PROXY_PUBLICATION_CONTEXT="$context" \
      CODEX_RESPONSES_PROXY_GITHUB_ALLOWED_SIGNERS="$tmp/allowed/github" \
    CODEX_RESPONSES_PROXY_GITHUB_SIGNING_KEY="$key" \
    CODEX_RESPONSES_PROXY_RELEASE_PYTHON="$mock_python" \
    CODEX_RESPONSES_PROXY_TEST_METADATA_LOG="$metadata_log" \
    CODEX_RESPONSES_PROXY_TEST_CANONICAL="$source" \
    CODEX_RESPONSES_PROXY_TEST_TAG="$target_tag" \
    CODEX_RESPONSES_PROXY_TEST_GITHUB_REMOTE="$remote" \
    GIT_SSH_COMMAND="$mock_ssh" \
    CODEX_RESPONSES_PROXY_GITHUB_REMOTE=github \
    "$@" sh "$script" "$target_tag"
  )
}

run_tag v1.0.0 >"$tmp/tagger.out" 2>"$tmp/tagger.err"

canonical_source=$(git -C "$source" rev-parse --show-toplevel)
first_repo=$(sed -n '1s/|.*//p' "$metadata_log")
second_repo=$(sed -n '2s/|.*//p' "$metadata_log")
[ -n "$first_repo" ] && [ "$first_repo" = "$second_repo" ] && [ "$first_repo" != "$canonical_source" ] || {
  echo 'GitHub tag creation did not keep validation inside one isolated provider checkout' >&2
  exit 1
}
grep -F -- '--provider github --prepare-release' "$metadata_log" >/dev/null || {
  echo 'GitHub tag creation bypassed provider-native release preparation' >&2
  exit 1
}
grep -F -- '--provider github --tag v1.0.0' "$metadata_log" >/dev/null || {
  echo 'GitHub tag creation bypassed exact provider-native tag validation' >&2
  exit 1
}
[ "$(wc -l < "$metadata_log" | tr -d ' ')" = 2 ] || {
  echo 'GitHub tag creation ran an unexpected cross-Forge metadata preflight' >&2
  exit 1
}
git -C "$remote" rev-parse --verify refs/tags/v1.0.0 >/dev/null
git -C "$remote" -c gpg.format=ssh -c gpg.ssh.program=ssh-keygen \
  -c gpg.ssh.allowedSignersFile="$tmp/allowed/github" verify-tag v1.0.0 >/dev/null 2>&1
[ "$(git -C "$remote" rev-parse 'v1.0.0^{commit}')" = "$(git -C "$remote" rev-parse 'refs/heads/main^{commit}')" ] || {
  echo 'GitHub release tag does not bind the GitHub main tip' >&2
  exit 1
}
[ "$(git -C "$remote" rev-parse 'v1.0.0^{}^{tree}')" = "$(git -C "$source" rev-parse 'HEAD^{tree}')" ] || {
  echo 'GitHub release tag tree differs from accepted local source tree' >&2
  exit 1
}
[ "$(git -C "$remote" rev-parse refs/tags/v0.9.0)" = "$existing_tag" ] || {
  echo 'GitHub tag creation changed an existing remote tag' >&2
  exit 1
}
remote_tag_count=$(git -C "$remote" for-each-ref --format='%(refname)' refs/tags | wc -l | tr -d ' ')
[ "$remote_tag_count" = 2 ] || {
  echo 'GitHub tag creation pushed more than the requested tag' >&2
  exit 1
}

# A provider-native target tag already present on GitHub must be rejected before
# GitHub metadata validation runs.
cp "$metadata_log" "$tmp/metadata-before-existing.log"
if run_tag v1.0.0 >"$tmp/existing.out" 2>"$tmp/existing.err"; then
  echo 'GitHub tag creation accepted an existing remote target tag' >&2
  exit 1
fi
grep -F 'GitHub tag already exists: v1.0.0' "$tmp/existing.err" >/dev/null || {
  echo 'existing-tag rejection returned an unclear error' >&2
  exit 1
}
cmp -s "$metadata_log" "$tmp/metadata-before-existing.log" || {
  echo 'existing GitHub target tag reached metadata validation' >&2
  exit 1
}

echo 'GitHub provider tag creation contract: OK'
