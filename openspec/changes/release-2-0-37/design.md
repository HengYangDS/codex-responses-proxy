## Context

The preceding generation implemented command discoverability and advanced the
sole version carrier to 2.0.37. Its post-archive source is already integrated
into `dev`; publication, installation, and runtime acceptance remain separate
external effects.

## Decision

Create one release-only generation on top of that accepted product state. This
produces a fresh exact-HEAD proof bound only to the release Commitment, instead
of reusing or modifying historical proof records. Existing tags and releases
remain immutable.

## Delivery Boundary

The Change ends after proof and archive. Candidate integration, accepted
closeout, independent Forge publication, asset verification, installation,
runtime acceptance, and lane retirement each require their own fresh receipt.
