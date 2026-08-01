#!/bin/sh
# Verify a provider-native signed release tag against an explicit trust anchor.
set -eu

repo=${1:-.}
tag=${2:?usage: check-release-tag-signature.sh [repository] <v<semver>> <gitlab|github>}
provider=${3:?usage: check-release-tag-signature.sh [repository] <v<semver>> <gitlab|github>}

display_tag=${tag#github/}
case "$display_tag" in
  v[0-9]*.[0-9]*.[0-9]*) ;;
  *) echo "release tag must be v<semver>: $tag" >&2; exit 2 ;;
esac
case "$provider" in
  gitlab|github) ;;
  *) echo "release provider must be gitlab or github" >&2; exit 2 ;;
esac

root=$(CDPATH= cd -- "$repo" && pwd)
anchor=${CODEX_RESPONSES_PROXY_RELEASE_ALLOWED_SIGNERS:-}
[ -f "$anchor" ] || { echo "$provider release trust must be supplied with CODEX_RESPONSES_PROXY_RELEASE_ALLOWED_SIGNERS" >&2; exit 2; }
git -C "$root" rev-parse --verify "refs/tags/$tag" >/dev/null
git -C "$root" -c gpg.format=ssh -c gpg.ssh.program=ssh-keygen \
  -c gpg.ssh.allowedSignersFile="$anchor" verify-tag "$tag" >/dev/null
printf '%s release tag signature: OK (%s)\n' "$provider" "$tag"
