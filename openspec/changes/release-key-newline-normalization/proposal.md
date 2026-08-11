# Normalize release signing key material

## Why

GitLab file variables may omit the terminal newline from an OpenSSH private key.
OpenSSH then rejects otherwise valid release credentials, so a verified tag can
finish every build gate and still fail only at asset publication.

## What changes

- Normalize the caller-provided signing key into an ephemeral `0600` file before
  invoking OpenSSH.
- Keep the original secret, trust anchor, assets, and Forge variables unchanged.
- Cover the exact no-terminal-newline form with a regression test.

## Boundaries

This change does not alter release identity, tags, Forge coupling, long-lived
credentials, product runtime behavior, or Codex state.
