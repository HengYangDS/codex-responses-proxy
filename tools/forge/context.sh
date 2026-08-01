#!/bin/sh
# Load caller-owned Forge publication identity and OpenSSH-agent capability.

publication_error() {
  echo "$*" >&2
  exit 2
}

load_publication_context() {
  provider=$1
  context=${CODEX_RESPONSES_PROXY_PUBLICATION_CONTEXT:-}
  [ -f "$context" ] || publication_error \
    "publication context must be supplied with CODEX_RESPONSES_PROXY_PUBLICATION_CONTEXT"
  record=$(python3 - "$context" "$provider" <<'PY'
import re
import sys
import tomllib
from pathlib import Path

context = tomllib.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if context.get("schema-version") != 1:
    raise SystemExit("unsupported publication context schema")
provider = context.get(sys.argv[2])
if not isinstance(provider, dict):
    raise SystemExit("Forge publication context is unavailable")
fields = tuple(
    provider.get(key)
    for key in (
        "actor-name",
        "actor-email",
        "active-signing-fingerprint",
    )
)
if not all(isinstance(value, str) and value and "\t" not in value for value in fields):
    raise SystemExit("Forge publication identity is incomplete")
if not re.fullmatch(r"SHA256:[A-Za-z0-9+/]+", fields[2]):
    raise SystemExit("provider signing fingerprint is invalid")
print("\t".join(fields))
PY
  ) || publication_error "invalid publication context for $provider"
  tab=$(printf '\t')
  old_ifs=$IFS
  IFS=$tab
  set -- $record
  IFS=$old_ifs
  [ "$#" -eq 3 ] || publication_error "invalid publication context record for $provider"
  publication_name=$1
  publication_email=$2
  publication_fingerprint=$3
}

select_agent_signing_key() {
  destination=$1
  [ -n "${SSH_AUTH_SOCK:-}" ] || publication_error "OpenSSH agent is unavailable"
  ssh_add=$(command -v ssh-add) || publication_error "OpenSSH ssh-add is unavailable"
  # Signing is intentionally independent of user-global Git configuration.
  # A configured wrapper may be workstation- or identity-specific; the product
  # accepts only the standard OpenSSH program resolved from the caller's PATH.
  publication_signing_program=$(command -v ssh-keygen) || publication_error \
    "OpenSSH ssh-keygen is unavailable"
  candidates="$destination.candidates"
  "$ssh_add" -L >"$candidates" 2>/dev/null || publication_error "OpenSSH agent has no signing keys"
  selected=
  while IFS= read -r line; do
    key=$(printf '%s\n' "$line" | awk 'NF >= 2 {print $1 " " $2}')
    [ -n "$key" ] || continue
    fingerprint=$(printf '%s\n' "$key" | "$publication_signing_program" -lf - -E sha256 2>/dev/null | awk 'NR == 1 {print $2}')
    [ "$fingerprint" = "$publication_fingerprint" ] || continue
    selected=$key
    break
  done <"$candidates"
  [ -n "$selected" ] || publication_error "required provider signing fingerprint is not loaded"
  printf '%s\n' "$selected" >"$destination"
  "$ssh_add" -T "$destination" >/dev/null 2>&1 || publication_error "loaded provider key cannot sign"
  publication_signing_key=$destination
}
