## ADDED Requirements

### Requirement: Remote branch namespace is explicit

Remote publication SHALL accept only `main`, `dev`, and `proposal/*` branch
refs. Local governance refs including `candidate/*` and `work/*` MUST fail
before a network mutation.

#### Scenario: A local work lane is pushed

- **WHEN** a push includes a `refs/heads/work/*` or `refs/heads/candidate/*`
  destination
- **THEN** the pre-push owner rejects the complete push
- **AND** the remote receives no ref update.

#### Scenario: A shared proposal is pushed

- **WHEN** a push targets `main`, `dev`, or `proposal/*`
- **THEN** branch namespace admission passes
- **AND** ordinary ETHOS and Forge admission still apply.

## MODIFIED Requirements

### Requirement: Provider identities are independent

GitLab SHALL retain accepted commits in its verified identity domain. GitHub
SHALL use its verified identity domain for an equivalent projection. Each Forge
SHALL build, sign, verify, and publish its own release assets without querying,
waiting for, authenticating to, or downloading from the other Forge.

#### Scenario: Forge emails differ

- **WHEN** the two Forges require different verified emails
- **THEN** their commit IDs differ
- **AND** their corresponding trees are equal.

#### Scenario: One publication plane is unavailable

- **WHEN** one Forge API, runner, tag pipeline, or Release service fails
- **THEN** the other Forge can complete its own publication
- **AND** no cross-Forge credential or asset dependency blocks it.

#### Scenario: Independent releases are audited

- **WHEN** both Forge Releases exist
- **THEN** each exact asset set and signature is verified in its own trust domain
- **AND** common-platform archives and manifests have equal digests
- **AND** provider-specific checksum signatures are not required to be equal.

### Requirement: Native executable acceptance

The release owner SHALL build one self-contained executable on the actual
target platform, exercise its public CLI and real handoff behavior, run it with
Python absent from `PATH`, and package a manifest-bound native asset. A hosted
job MUST prove its runtime architecture before assigning a platform identifier.

#### Scenario: A platform asset is published

- **WHEN** a release archive for a supported OS and architecture is admitted
- **THEN** its executable passed black-box help, version, status, manifest, and
  service-start checks in a pristine native environment
- **AND** Python was absent from the product execution path.

#### Scenario: Minimal Linux verifies the native executable

- **WHEN** a hosted Linux matrix or quality job starts from its declared
  minimal base image
- **THEN** the provider projection installs the operating-system tools required
  by the repository-owned native executable gate
- **AND** every supported Python line executes that gate without depending on
  private runner image state
- **AND** a contract test rejects omission of the declared prerequisite.

#### Scenario: Local release runs without a Forge

- **WHEN** a contributor runs the locked release session in a clean checkout
- **THEN** the current-platform executable and release bundle are fully accepted
- **AND** no Forge API, remote ref, hosted credential, or published artifact is required.

#### Scenario: Linux x86_64 is built on an ARM host

- **WHEN** a Docker executor runs on an ARM workstation
- **THEN** the release job explicitly selects an amd64 container
- **AND** packaging fails unless the container reports an x86_64-compatible machine.
