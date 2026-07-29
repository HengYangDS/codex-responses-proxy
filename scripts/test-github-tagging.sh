#!/bin/sh
# Exercise the two-provider GitHub tag sequence without a network connection.
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
mock_python="$tmp/mock-python3"
metadata_log="$tmp/metadata.log"
mkdir -p "$home" "$tmp/allowed"
: > "$global_config"
ssh-keygen -q -t ed25519 -N '' -f "$key"
public=$(awk '{print $1" "$2}' "$key.pub")
printf 'heng.yang.ds@hotmail.com namespaces="git" %s\n' "$public" > "$tmp/allowed/gitlab"
printf 'hengyang.2003@tsinghua.org.cn namespaces="git" %s\n' "$public" > "$tmp/allowed/github"

cat > "$mock_ssh" <<'EOF_SSH'
#!/bin/sh
case "$*" in
  *git-upload-pack*) exec git-upload-pack "${DMX_TEST_GITHUB_REMOTE:?}" ;;
  *git-receive-pack*) exec git-receive-pack "${DMX_TEST_GITHUB_REMOTE:?}" ;;
esac
exit 0
EOF_SSH
chmod +x "$mock_ssh"

cat > "$signing_wrapper" <<'EOF_SIGN'
#!/bin/sh
set -eu
printf '%s\n' "$*" >> "${DMX_TEST_SIGNING_LOG:?}"
exec ssh-keygen "$@"
EOF_SIGN
chmod +x "$signing_wrapper"

cat > "$mock_python" <<'EOF_PYTHON'
#!/bin/sh
set -eu
checker=$1
repo=${checker%/scripts/check_release_metadata.py}
repo=$(CDPATH= cd -- "$repo" && pwd)
canonical=$(git -C "${DMX_TEST_CANONICAL:?}" rev-parse --show-toplevel)
printf '%s|%s\n' "$repo" "$*" >> "${DMX_TEST_METADATA_LOG:?}"
case "$*" in
  *'--provider gitlab --tag '*)
    test "$repo" = "$canonical" || {
      echo 'GitLab metadata preflight ran outside the canonical checkout' >&2
      exit 90
    }
    ;;
  *'--provider github --tag '*)
    test "$repo" != "$canonical" || {
      echo 'GitHub metadata preflight ran in the canonical GitLab checkout' >&2
      exit 91
    }
    git -C "$repo" show-ref --verify --quiet "refs/tags/${DMX_TEST_TAG:?}" || {
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
cp "$root/scripts/check_release_metadata.py" "$source/scripts/"
chmod +x "$source/scripts/check-release-tag-signature.sh" "$source/scripts/check_release_metadata.py"
printf 'release source\n' > "$source/README.md"
git -C "$source" add .
git -C "$source" commit -qm 'release source'
git -C "$source" -c gpg.format=ssh -c user.signingkey="$key" tag -s -a v1.0.0 -m 'GitLab release identity'

projection="$tmp/projection"
git clone -q --no-local "file://$source" "$projection"
git -C "$projection" tag -d v1.0.0 >/dev/null
FILTER_BRANCH_SQUELCH_WARNING=1 git -C "$projection" filter-branch -f --env-filter '
  GIT_AUTHOR_NAME="Yang HENG"
  GIT_AUTHOR_EMAIL="hengyang.2003@tsinghua.org.cn"
  GIT_COMMITTER_NAME="Yang HENG"
  GIT_COMMITTER_EMAIL="hengyang.2003@tsinghua.org.cn"
' -- main >/dev/null 2>&1
git -C "$projection" remote set-url origin "file://$remote"
git -C "$projection" push -q origin main
git -C "$remote" symbolic-ref HEAD refs/heads/main
git -C "$projection" -c user.name='Yang HENG' -c user.email='hengyang.2003@tsinghua.org.cn' \
  -c user.useConfigOnly=true -c gpg.format=ssh -c gpg.ssh.program="$signing_wrapper" \
  -c user.signingkey="$key" tag -s -a v0.9.0 -m 'existing GitHub tag'
git -C "$projection" push -q origin refs/tags/v0.9.0:refs/tags/v0.9.0
existing_tag=$(git -C "$remote" rev-parse refs/tags/v0.9.0)

git -C "$source" remote add github git@github.com:test/codex-dmx-proxy.git
run_tag() {
  target_tag=$1
  shift
  (
    cd "$source"
    DMX_GITHUB_SIGNING_KEY="$key" \
    DMX_RELEASE_PYTHON="$mock_python" \
    DMX_TEST_METADATA_LOG="$metadata_log" \
    DMX_TEST_CANONICAL="$source" \
    DMX_TEST_TAG="$target_tag" \
    DMX_TEST_GITHUB_REMOTE="$remote" \
    GIT_SSH_COMMAND="$mock_ssh" \
    DMX_GITHUB_REMOTE=github \
    "$@" sh "$script" "$target_tag"
  )
}

run_tag v1.0.0 >/dev/null

canonical_source=$(git -C "$source" rev-parse --show-toplevel)
[ "$(sed -n '1p' "$metadata_log")" = "$canonical_source|$canonical_source/scripts/check_release_metadata.py --provider gitlab --tag v1.0.0" ] || {
  echo 'GitHub tag creation did not first validate the exact canonical GitLab tag' >&2
  exit 1
}
second_repo=$(sed -n '2s/|.*//p' "$metadata_log")
[ -n "$second_repo" ] && [ "$second_repo" != "$canonical_source" ] || {
  echo 'GitHub tag creation did not isolate provider validation' >&2
  exit 1
}
second_checker=$(sed -n '2s/^[^|]*|\([^ ]*\).*/\1/p' "$metadata_log")
second_checker_normalized=$(printf '%s\n' "$second_checker" | sed 's://*:/:g')
case "$second_checker_normalized" in "$second_repo"/scripts/check_release_metadata.py) ;; *)
  echo 'GitHub metadata checker did not come from the isolated projection' >&2
  exit 1
;; esac
grep -F -- "$second_checker --provider github --tag v1.0.0" "$metadata_log" >/dev/null || {
  echo 'GitHub tag creation used the wrong provider namespace' >&2
  exit 1
}
[ "$(wc -l < "$metadata_log" | tr -d ' ')" = 2 ] || {
  echo 'GitHub tag creation ran an unexpected metadata preflight' >&2
  exit 1
}
grep -F -- '-Y sign' "$signing_log" >/dev/null || {
  echo 'GitHub tag creation bypassed the configured SSH signing program' >&2
  exit 1
}
git -C "$remote" rev-parse --verify refs/tags/v1.0.0 >/dev/null
git -C "$remote" -c gpg.format=ssh -c gpg.ssh.program=ssh-keygen \
  -c gpg.ssh.allowedSignersFile="$tmp/allowed/github" verify-tag v1.0.0 >/dev/null
[ "$(git -C "$remote" rev-parse 'v1.0.0^{commit}')" = "$(git -C "$remote" rev-parse 'refs/heads/main^{commit}')" ] || {
  echo 'GitHub release tag does not bind the GitHub main tip' >&2
  exit 1
}
[ "$(git -C "$remote" rev-parse 'v1.0.0^{}^{tree}')" = "$(git -C "$source" rev-parse 'v1.0.0^{}^{tree}')" ] || {
  echo 'GitHub release tag tree differs from GitLab release tag tree' >&2
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

# A provider-native target tag already present on GitHub must be rejected after
# only the canonical GitLab phase; GitHub metadata validation must not run.
cp "$metadata_log" "$tmp/metadata-before-existing.log"
if run_tag v1.0.0 >"$tmp/existing.out" 2>"$tmp/existing.err"; then
  echo 'GitHub tag creation accepted an existing remote target tag' >&2
  exit 1
fi
grep -F 'GitHub tag already exists: v1.0.0' "$tmp/existing.err" >/dev/null || {
  echo 'existing-tag rejection returned an unclear error' >&2
  exit 1
}
existing_before=$(wc -l < "$tmp/metadata-before-existing.log" | tr -d ' ')
existing_after=$(wc -l < "$metadata_log" | tr -d ' ')
[ "$existing_after" = "$((existing_before + 1))" ] || {
  echo 'existing GitHub target tag reached provider validation' >&2
  exit 1
}
tail -n 1 "$metadata_log" | grep -F -- '--provider gitlab --tag v1.0.0' >/dev/null || {
  echo 'existing GitHub target tag bypassed canonical validation order' >&2
  exit 1
}

# The canonical GitLab tag must peel to canonical main HEAD before any
# provider-specific metadata checker is invoked.
printf 'later source\n' >> "$source/README.md"
git -C "$source" add README.md
git -C "$source" commit -qm 'later source'
cp "$metadata_log" "$tmp/metadata-before-head.log"
if run_tag v1.0.0 >"$tmp/head.out" 2>"$tmp/head.err"; then
  echo 'GitHub tag creation accepted a GitLab tag that does not bind HEAD' >&2
  exit 1
fi
grep -F 'does not bind canonical HEAD' "$tmp/head.err" >/dev/null || {
  echo 'wrong-HEAD rejection returned an unclear error' >&2
  exit 1
}
cmp -s "$metadata_log" "$tmp/metadata-before-head.log" || {
  echo 'wrong-HEAD GitLab tag was checked after provider validation' >&2
  exit 1
}

echo 'GitHub provider tag creation contract: OK'
