# Preserve signing-key file identity

## Why

The shared signer currently copies every private key into a temporary file.
That repairs a GitLab POSIX file variable whose terminal newline was removed,
but on Windows the copy loses the secret provider's accepted ACL and OpenSSH
rejects the otherwise valid key.

## What changes

- Sign directly with a complete provider-owned key file.
- Create a private temporary copy only when a POSIX key lacks its terminal
  newline.
- Keep malformed Windows input fail-closed instead of manufacturing ACLs.

## Boundaries

The release identity, trust anchor, Forge workflows, tags, assets, and product
runtime remain unchanged.
