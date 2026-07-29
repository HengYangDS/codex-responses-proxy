#!/bin/sh
# Exercise complete GitLab history normalization without network access.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
script="$root/scripts/project-gitlab-forge.sh"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/codex-dmx-proxy-gitlab-projection.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

source="$tmp/source"
remote="$tmp/gitlab.git"
home="$tmp/home"
key="$tmp/signing"
wrapper="$tmp/signing-wrapper"
mkdir -p "$home"
ssh-keygen -q -t ed25519 -N '' -f "$key"
public=$(awk '{print $1" "$2}' "$key.pub")
cat > "$wrapper" <<'EOF'
#!/bin/sh
exec /usr/bin/ssh-keygen "$@"
EOF
chmod +x "$wrapper"

export HOME="$home"
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/dev/null
git init -q --bare "$remote"
git init -q -b main "$source"
git -C "$source" config user.name 'Mixed Author'
git -C "$source" config user.email 'mixed@example.test'
git -C "$source" config user.useConfigOnly true
mkdir -p "$source/packaging/release" "$source/scripts"
printf 'heng.yang.ds@hotmail.com namespaces="git" %s\n' "$public" > "$source/packaging/release/gitlab-allowed-signers"
cp "$root/scripts/rewrite-provider-history.py" "$source/scripts/"
printf 'first\n' > "$source/README.md"
git -C "$source" add .
git -C "$source" commit -qm first
printf 'second\n' >> "$source/README.md"
git -C "$source" add .
git -C "$source" commit -qm second
source_tree=$(git -C "$source" rev-parse HEAD^{tree})
source_refs=$(git -C "$source" for-each-ref --format='%(refname) %(objectname)' | LC_ALL=C sort)
git -C "$source" remote add origin "file://$remote"

(
  cd "$source"
  DMX_GITLAB_SIGNING_KEY="$key.pub" \
    DMX_GITLAB_SSH_SIGNING_PROGRAM="$wrapper" \
    sh "$script"
) >/dev/null

[ "$(git -C "$source" for-each-ref --format='%(refname) %(objectname)' | LC_ALL=C sort)" = "$source_refs" ] || {
  echo 'GitLab projection rewrote source refs' >&2
  exit 1
}
[ "$(git -C "$remote" rev-parse main^{tree})" = "$source_tree" ] || {
  echo 'GitLab projection changed the source tree' >&2
  exit 1
}
if git -C "$remote" log main --format='%ae%n%ce' | grep -Fv -x 'heng.yang.ds@hotmail.com' | grep -q .; then
  echo 'GitLab projection retains a non-GitLab identity' >&2
  exit 1
fi
for commit in $(git -C "$remote" rev-list main); do
  git -C "$remote" -c gpg.format=ssh \
    -c gpg.ssh.allowedSignersFile="$source/packaging/release/gitlab-allowed-signers" \
    verify-commit "$commit" >/dev/null
done

echo 'GitLab provider projection isolation contract: OK'
