# DR-0004: Publish Locally Complete Releases through Independent Forges

- Status: accepted
- Date: 2026-08-07

## Context

GitLab and GitHub are separate transport, account, CI, Release, and asset
domains. Creating different Git histories or tag objects for them destroys exact
product identity. Making either workflow query, authenticate to, wait for, or
publish through the other creates a common failure path and prevents local closure.

## Decision

A clean accepted source tree can build, verify, install, exercise, and uninstall
without a Forge. The product commit and annotated release tag are created and
signed once in local Git, then published unchanged to either optional Forge.
GitLab and GitHub independently authenticate transport, verify the same public
identity, run CI, and publish complete Release assets. Neither consumes the other.

Cross-Forge comparison is read-only and occurs only after both publications
exist. It requires exact branch commit OIDs and tag object OIDs, then compares
common asset bytes and each Forge's provider-local delivery evidence.

## Consequences

One Forge can remain usable during an outage of the other. One-sided success is
reported as one-sided publication, never as a dual release. Push credentials may
differ, but they never change Git objects. Product source contains no personal
private key, credential, or checkout path.

## Revisit Trigger

Revisit if one publication plane is retired or an external attestation authority
replaces local Git object signatures. Multiple organizational endorsements should
remain detached attestations over one product SHA, not alternate Git histories.
