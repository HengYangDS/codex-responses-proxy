# DR-0004: Publish Locally Complete Releases through Independent Forges

- Status: accepted
- Date: 2026-08-07

## Context

GitLab and GitHub are separate identity, CI, trust, tag, Release, and asset
domains. Making either workflow query, authenticate to, wait for, or publish
through the other creates a common failure path and prevents local closure.

## Decision

A clean accepted source tree can build, verify, install, exercise, and
uninstall without a Forge. GitLab and GitHub independently project the same
accepted source, verify provider-native provenance, and build and publish their
own complete release assets. Neither Forge consumes the other's release.

Cross-Forge comparison is read-only and occurs only after both publications
exist. It compares source meaning and common asset bytes while verifying each
provider-native signature against its own trust input.

## Consequences

One Forge can remain usable during an outage of the other. One-sided success is
reported as one-sided publication, never as a dual release. Product source
contains no personal signer, actor, email, key, fingerprint, credential, or
checkout path.

## Revisit Trigger

Revisit if one publication plane is retired or an organization adopts a single
external release authority that replaces both Forge-native release domains.
