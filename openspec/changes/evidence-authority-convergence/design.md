## Context

Thirty-one Claims point to thirty-two Chronicle files. Every Claim resolves to
an existing OpenSpec archive; the one Chronicle not selected by a Claim is also
covered by the `ci-log-hygiene` archive and Changelog. No current command writes
or selects either family.

## Decision

Delete the entire tracked taxonomy instead of preserving a reader, migration
shim, empty root, or deprecated family. Current result authority is:

```text
repository facts + tests + OpenSpec/Git history + release artifacts
                            |
                            v
                 ETHOS-selected Attestation
```

The documentation explains proof boundaries but does not become another
carrier. The quality gate stops recognizing legacy directories instead of
encoding a prohibition framework for artifacts that no longer exist.

## Migration

1. Record the machine inventory and confirm every historical record has an
   existing canonical archive or release-history carrier.
2. Delete Claims, Chronicles, family configuration, consumers, tests, and
   naming exemptions together.
3. Run repository quality, Python 3.12/3.13/3.14, exact-HEAD proof, archive,
   post-archive proof, integration, and retirement.

## Risks

A historical file could contain unique semantics. The inventory prevents this
by resolving every Claim to its archive and separately inspecting orphan
Chronicles before deletion.
