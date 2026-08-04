## ADDED Requirements

### Requirement: Private GitLab Release assets use authenticated provider transport

The publication verifier SHALL read each GitLab Release asset through the
caller's authenticated GitLab API authority while preserving the exact asset
URL recorded by the Release and the existing byte-level digest comparison.

#### Scenario: Private package asset requires authentication

- **WHEN** a GitLab Release records a required package asset whose anonymous
  HTTP request is unauthorized
- **THEN** the verifier reads that exact asset through the authenticated GitLab
  API transport
- **AND** it compares the resulting bytes with the corresponding GitHub Release
  asset before publication can verify.

#### Scenario: GitLab authentication is unavailable

- **WHEN** the configured GitLab provider transport cannot authenticate or read
  a required Release asset
- **THEN** publication verification fails closed
- **AND** it neither falls back to an untrusted asset nor reports cross-Forge
  publication as verified.
