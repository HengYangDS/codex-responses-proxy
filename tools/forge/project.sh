#!/bin/sh
# Project one accepted source history into a Forge-specific commit identity.
set -eu

usage() {
  cat >&2 <<'USAGE'
usage: project.sh --provider <gitlab|github> [--source-ref <ref>]
                  [--remote <name>] [--map-output <path>]

GitLab receives the accepted canonical commits unchanged. GitHub receives an
append-only identity projection with identical trees, messages, dates, and
parent topology. Every projected commit uses the selected Forge actor and a
trusted signature. Existing remote history is never rewritten or force-pushed.
USAGE
  exit 2
}

provider=
source_ref=${CODEX_RESPONSES_PROXY_SOURCE_REF:-HEAD}
remote=
map_output=

while [ "$#" -gt 0 ]; do
  case "$1" in
    --provider) provider=${2:?missing provider}; shift ;;
    --source-ref) source_ref=${2:?missing source ref}; shift ;;
    --remote) remote=${2:?missing remote}; shift ;;
    --map-output) map_output=${2:?missing map output}; shift ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
  shift
done

case "$provider" in
  gitlab) remote=${remote:-${CODEX_RESPONSES_PROXY_GITLAB_REMOTE:-origin}} ;;
  github) remote=${remote:-${CODEX_RESPONSES_PROXY_GITHUB_REMOTE:-github}} ;;
  *) echo "provider must be gitlab or github" >&2; exit 2 ;;
esac
case "$source_ref" in '') echo "source ref must not be empty" >&2; exit 2 ;; esac

root=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "run inside a Git worktree" >&2
  exit 2
}
git diff --quiet && git diff --cached --quiet || {
  echo "refusing Forge projection with a dirty checkout" >&2
  exit 2
}

script_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=tools/forge/context.sh
. "$script_root/context.sh"
load_publication_context "$provider"

canonical_anchor=${CODEX_RESPONSES_PROXY_GITLAB_COMMIT_ALLOWED_SIGNERS:-}
provider_anchor_variable=CODEX_RESPONSES_PROXY_$(printf '%s' "$provider" | tr '[:lower:]' '[:upper:]')_COMMIT_ALLOWED_SIGNERS
eval "provider_anchor=\${$provider_anchor_variable:-}"
[ -f "$canonical_anchor" ] || publication_error \
  "canonical GitLab commit trust must be supplied with CODEX_RESPONSES_PROXY_GITLAB_COMMIT_ALLOWED_SIGNERS"
[ -f "$provider_anchor" ] || publication_error \
  "$provider commit trust must be supplied with $provider_anchor_variable"

source=$(git rev-parse --verify --end-of-options "$source_ref^{commit}") || {
  echo "source ref is not a commit: $source_ref" >&2
  exit 2
}
source_tree=$(git rev-parse "$source^{tree}")
remote_url=$(git config --local --get "remote.$remote.url" 2>/dev/null) || {
  echo "$provider remote is not configured: $remote" >&2
  exit 2
}

workspace=$(mktemp -d "${TMPDIR:-/tmp}/codex-responses-proxy-$provider-projection.XXXXXX")
cleanup() { rm -rf "$workspace"; }
trap cleanup EXIT HUP INT TERM
repository="$workspace/repository"
map_rows="$workspace/map.tsv"
created_rows="$workspace/created.tsv"
: >"$map_rows"
: >"$created_rows"

git_transport() {
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git "$@"
}

commit_email_and_signature_are_valid() {
  repository_path=$1
  commit=$2
  expected_email=$3
  allowed_signers=$4
  [ "$(git -C "$repository_path" show -s --format=%ae "$commit")" = "$expected_email" ] &&
    [ "$(git -C "$repository_path" show -s --format=%ce "$commit")" = "$expected_email" ] &&
    git_transport -C "$repository_path" \
      -c gpg.format=ssh \
      -c gpg.ssh.program=ssh-keygen \
      -c gpg.ssh.allowedSignersFile="$allowed_signers" \
      verify-commit "$commit" >/dev/null 2>&1
}

gitlab_email=$(CODEX_RESPONSES_PROXY_PUBLICATION_CONTEXT=${CODEX_RESPONSES_PROXY_PUBLICATION_CONTEXT:-} \
  sh -c '. "$1"; load_publication_context gitlab; printf %s "$publication_email"' _ "$script_root/context.sh")
for commit in $(git rev-list "$source"); do
  commit_email_and_signature_are_valid "$root" "$commit" "$gitlab_email" "$canonical_anchor" || {
    echo "canonical GitLab identity or signature is invalid: $commit" >&2
    exit 1
  }
done

git_transport clone --quiet --no-local --no-tags "file://$root" "$repository"
git -C "$repository" remote remove origin 2>/dev/null || true
git -C "$repository" remote add target "$remote_url"
remote_tip=$(git_transport -C "$repository" ls-remote --heads target refs/heads/main | awk 'NR == 1 {print $1}')
if [ -n "$remote_tip" ]; then
  git_transport -C "$repository" fetch --quiet --no-tags target \
    refs/heads/main:refs/remotes/target/main
fi

write_map() {
  projected=$1
  base_source=$2
  base_projected=$3
  [ -n "$map_output" ] || return 0
  mkdir -p "$(dirname -- "$map_output")"
  python3 - "$provider" "$source" "$projected" "$source_tree" "$base_source" "$base_projected" \
    "$map_rows" "$created_rows" "$map_output" <<'PY'
import json
import os
import sys
from pathlib import Path

provider, source, projected, tree, base_source, base_projected, rows, created, output = sys.argv[1:]

def pairs(path: str) -> list[dict[str, str]]:
    return [
        {"source": source_oid, "projected": projected_oid}
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line
        for source_oid, projected_oid in (line.split("\t", 1),)
    ]

payload = {
    "schema_version": 1,
    "provider": provider,
    "source_commit": source,
    "projected_commit": projected,
    "tree": tree,
    "base_source_commit": base_source or None,
    "base_projected_commit": base_projected or None,
    "mapping": pairs(rows),
    "created": pairs(created),
}
destination = Path(output)
temporary = destination.with_name(destination.name + ".tmp")
temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.replace(temporary, destination)
PY
}

if [ "$provider" = gitlab ]; then
  if [ -n "$remote_tip" ]; then
    git -C "$repository" merge-base --is-ancestor "$remote_tip" "$source" || {
      echo "GitLab main is not an ancestor of canonical source; forward-only projection refused" >&2
      exit 1
    }
  fi
  printf '%s\t%s\n' "$source" "$source" >>"$map_rows"
  git_transport -C "$repository" push target "$source:refs/heads/main"
  write_map "$source" "$source" "$source"
  printf 'GitLab canonical projection synchronized: %s\n' "$source"
  exit 0
fi

select_agent_signing_key "$workspace/signing-key.pub"

commit_fingerprint() {
  repository_path=$1
  commit=$2
  message_file="$workspace/fingerprint-message"
  parent_count=$(git -C "$repository_path" show -s --format=%P "$commit" | awk '{print NF}')
  git -C "$repository_path" cat-file commit "$commit" | sed '1,/^$/d' >"$message_file"
  {
    printf 'parents=%s\n' "$parent_count"
    git -C "$repository_path" show -s --format='%T%n%aI%n%cI' "$commit"
    printf '%s\n' '---message---'
    cat "$message_file"
  } | git hash-object --stdin
}

canonical_commits=$(git -C "$repository" rev-list --reverse --topo-order "$source")
base_source=
base_projected=
if [ -n "$remote_tip" ]; then
  for commit in $(git -C "$repository" rev-list "$remote_tip"); do
    commit_email_and_signature_are_valid "$repository" "$commit" "$publication_email" "$provider_anchor" || {
      echo "existing GitHub identity or signature is invalid: $commit" >&2
      exit 1
    }
  done
  remote_fingerprint=$(commit_fingerprint "$repository" "$remote_tip")
  matches=
  for canonical_commit in $canonical_commits; do
    [ "$(commit_fingerprint "$repository" "$canonical_commit")" = "$remote_fingerprint" ] || continue
    matches="${matches}${matches:+
}$canonical_commit"
  done
  match_count=$(printf '%s\n' "$matches" | awk 'NF {count++} END {print count + 0}')
  [ "$match_count" -eq 1 ] || {
    echo "GitHub branch tree diverges from canonical history; found $match_count identity-neutral matches" >&2
    exit 1
  }
  base_source=$matches
  base_projected=$remote_tip

  for canonical_commit in $canonical_commits; do
    canonical_fingerprint=$(commit_fingerprint "$repository" "$canonical_commit")
    projected_matches=
    for projected_commit in $(git -C "$repository" rev-list "$remote_tip"); do
      [ "$(commit_fingerprint "$repository" "$projected_commit")" = "$canonical_fingerprint" ] || continue
      projected_matches="${projected_matches}${projected_matches:+
}$projected_commit"
    done
    projected_count=$(printf '%s\n' "$projected_matches" | awk 'NF {count++} END {print count + 0}')
    [ "$projected_count" -le 1 ] || {
      echo "canonical commit has ambiguous GitHub history matches: $canonical_commit" >&2
      exit 1
    }
    [ "$projected_count" -eq 1 ] || continue
    printf '%s\t%s\n' "$canonical_commit" "$projected_matches" >>"$map_rows"
  done
fi

lookup_projected_parent() {
  source_parent=$1
  awk -F '\t' -v source="$source_parent" '$1 == source {print $2; exit}' "$map_rows"
}

if [ -n "$base_source" ]; then
  new_commits=$(git -C "$repository" rev-list --reverse --topo-order "$base_source..$source")
  projected=$remote_tip
else
  new_commits=$canonical_commits
  projected=
fi

message_file="$workspace/commit-message"
for source_commit in $new_commits; do
  set --
  for source_parent in $(git -C "$repository" show -s --format=%P "$source_commit"); do
    projected_parent=$(lookup_projected_parent "$source_parent")
    [ -n "$projected_parent" ] || {
      echo "canonical parent has no GitHub projection: $source_parent" >&2
      exit 1
    }
    set -- "$@" -p "$projected_parent"
  done
  git -C "$repository" cat-file commit "$source_commit" | sed '1,/^$/d' >"$message_file"
  projected=$(
    GIT_AUTHOR_NAME="$publication_name" \
    GIT_AUTHOR_EMAIL="$publication_email" \
    GIT_AUTHOR_DATE="$(git -C "$repository" show -s --format=%aI "$source_commit")" \
    GIT_COMMITTER_NAME="$publication_name" \
    GIT_COMMITTER_EMAIL="$publication_email" \
    GIT_COMMITTER_DATE="$(git -C "$repository" show -s --format=%cI "$source_commit")" \
    git_transport -C "$repository" \
      -c gpg.format=ssh \
      -c gpg.ssh.program="$publication_signing_program" \
      -c user.signingkey="$publication_signing_key" \
      commit-tree -S "$(git -C "$repository" show -s --format=%T "$source_commit")" "$@" \
      <"$message_file"
  )
  commit_email_and_signature_are_valid "$repository" "$projected" "$publication_email" "$provider_anchor" || {
    echo "generated GitHub commit does not satisfy provider trust: $projected" >&2
    exit 1
  }
  printf '%s\t%s\n' "$source_commit" "$projected" >>"$map_rows"
  printf '%s\t%s\n' "$source_commit" "$projected" >>"$created_rows"
done

[ -n "$projected" ] || {
  echo "GitHub projection produced no target commit" >&2
  exit 1
}
[ "$(git -C "$repository" rev-parse "$projected^{tree}")" = "$source_tree" ] || {
  echo "projected GitHub branch tree differs from canonical source" >&2
  exit 1
}
git -C "$repository" update-ref refs/heads/main "$projected"
git_transport -C "$repository" push target refs/heads/main:refs/heads/main
write_map "$projected" "$base_source" "$base_projected"
printf 'GitHub identity projection synchronized: %s\n' "$projected"
