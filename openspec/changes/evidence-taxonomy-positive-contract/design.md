## Context

`docs/evidence/README.md` explains acceptance evidence, while
`tools/quality/repository.py` independently embeds the admitted directory names.
The active specification and test also retain a retired directory name. That
creates duplicate policy and makes historical cleanup terminology part of the
present product contract.

## Decision

The canonical specification owns a small TOML block containing the durable
evidence family names and meanings. The quality gate reads that block with the
standard library TOML parser and validates physical top-level directories
against it. Documentation describes the same semantics for people but does not
mint a second machine policy.

Active tests use `unclassified` as a neutral unknown family. Archived OpenSpec
changes remain untouched because they are immutable records, not active policy.

## Boundaries

- Claims state bounded assertions suitable for machine verification.
- Chronicle entries retain human-readable historical execution context.
- Transient audits and generated reports remain tool outputs unless a future
  Change deliberately admits another durable family.
- Forge comparison stays owned by the Forge audit tool.

## Rollback

Revert this Change. No evidence payload or runtime data migration is involved.
