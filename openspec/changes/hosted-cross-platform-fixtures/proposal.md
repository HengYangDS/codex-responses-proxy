# Hosted Cross-Platform Fixtures

## Why

Hosted runners expose platform defaults that local verification does not own:
Git may create `main` during clone, and Windows text writes may translate an
OpenSSH private key to CRLF. Both make otherwise portable tests fail before the
behavior under test is reached.

## What Changes

- Reset the divergent fixture's existing `main` branch deterministically.
- Preserve temporary OpenSSH private-key bytes exactly on every platform.

## What Does Not Change

- Forge projection, signing, release, and product runtime semantics.
- Provider identities, trust anchors, or publication topology.
