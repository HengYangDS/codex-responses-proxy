## ADDED Requirements

### Requirement: Retained evidence has a current consumer and bounded lifetime

Every durable evidence carrier SHALL identify the exact revision, claim,
verifier, consumer, retention rule, and retirement condition that justify its
existence. Evidence without a current acceptance, publication, audit, or
recovery consumer SHALL be deleted rather than moved into another archive,
records tree, Claim family, Chronicle family, or compatibility taxonomy.

#### Scenario: Repository evidence is inventoried

- **WHEN** terminal convergence audits tracked and host-local evidence
- **THEN** every retained carrier names its current consumer and exact source revision
- **AND** duplicate, superseded, environment-bound, or consumerless carriers are removed.

#### Scenario: A transient verification completes

- **WHEN** a local, hosted, native, or Forge verification result has been bound
  into its authoritative Attestation or immutable release record
- **THEN** scratch reports, parity directories, downloaded assets, logs, and
  intermediate receipts are removed
- **AND** current acceptance remains reproducible from its authoritative sources.
