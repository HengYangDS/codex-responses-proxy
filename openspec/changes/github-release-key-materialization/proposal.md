# Complete GitHub release-key materialization

## Why

GitHub stored the private key as a text secret. Materialization omitted the
terminal newline required by the OpenSSH private-key format, and the Python
wrapper hid the actionable `ssh-keygen` diagnostic behind a traceback.

## What Changes

- Materialize the secret as one mode-`0600` file with a terminal newline.
- Preserve the concise OpenSSH rejection reason without a Python traceback.

## Non-goals

- No private-key parsing, copying in product code, fallback signer, or GitLab
  change.
