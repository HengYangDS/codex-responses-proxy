# Use one portable release-signing boundary

## Why

Release assembly copied private-key text into a temporary file. POSIX mode
changes did not establish a restrictive Windows ACL, so OpenSSH rejected the
copied key during native Windows verification.

## What Changes

- Accept one provider-owned private-key file path.
- Remove temporary private-key materialization from repository code.
- Give GitHub and GitLab the same signing input contract.
- Keep OpenSSH signature generation and independent verification unchanged.

## Non-goals

- No provider, runtime, release version, or trust-anchor change.
- No compatibility input for private-key text.
