## Context

Version 2.0.39 is the latest published and installed release. The accepted
source has since replaced heuristic quality gates with positive contracts,
clarified provider admission and information architecture, and updated the
locked development toolchain.

## Decision

Publish those compatible repository changes as 2.0.40. Keep `VERSION` as the
single version authority, preserve all existing tags and Releases, and build
each Forge's assets independently from an equivalent verified product tree.

## Delivery Boundary

The Change covers release identity and exact-source proof. Candidate
integration, accepted closeout, independent Forge publication, asset parity,
installation, runtime acceptance, and lane retirement remain separately
verified delivery effects.
