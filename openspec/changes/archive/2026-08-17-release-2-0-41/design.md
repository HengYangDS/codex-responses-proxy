## Context

Version 2.0.40 predates the accepted Forge-audit continuity repair. That repair
derives branch roles from repository policy, binds provenance to exact
projection receipts, fails closed on continuity drift, and replaces repeated
tag fetches with one bounded fetch.

## Decision

Publish the accepted repair as 2.0.41. Keep `VERSION` as the sole version
authority, preserve existing release history, and let GitLab and GitHub build
independently from equivalent verified product trees.

## Delivery Boundary

This Change owns release identity and exact-source proof. Candidate integration,
accepted closeout, provider-native publication, asset parity, installation,
runtime acceptance, and lane retirement remain separately verified effects.
