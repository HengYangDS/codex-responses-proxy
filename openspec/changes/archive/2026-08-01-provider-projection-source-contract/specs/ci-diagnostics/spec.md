## ADDED Requirements

### Requirement: Product identity is provider-neutral

The current repository, package, runtime, service, release, documentation, and
test surfaces SHALL identify the product as Codex Responses Proxy. Provider
names SHALL appear only in provider profiles, endpoints, or provider-specific
wire policies. Publication commands SHALL NOT contain a personal key path or
maintainer identity default, and SHALL fail immediately when explicit signing
inputs are unavailable.

#### Scenario: A new Responses provider is added

- **WHEN** another third-party Responses endpoint is admitted
- **THEN** it is represented as a provider profile or adapter
- **AND** no product, package, runtime, service, or environment namespace changes.

#### Scenario: Publication runs on another workstation

- **WHEN** an operator supplies provider identity and a public key available in
  an existing standard OpenSSH agent
- **THEN** the direct projector or tagger can sign without a maintainer-specific
  path, password prompt, Keychain bridge, private PTY, or temporary agent.

### Requirement: Provider projection separates source and target authority

Forge publication SHALL preserve the accepted signed commit graph and only fast-forward the target `main` branch. It SHALL NOT require a local `main`, recreate commits, rewrite attribution, or force-update a target. Expected child failures SHALL preserve their exit status without emitting a Python traceback.

#### Scenario: Accepted source is dev

- **WHEN** the clean canonical checkout is attached to `dev` and its current
  `HEAD` is selected for GitHub projection
- **THEN** GitHub `main` fast-forwards to that exact signed commit graph
- **AND** no local branch, commit, or existing tag is created, moved, or rewritten.

#### Scenario: Projection command rejects its invocation

- **WHEN** a provider projection child returns a nonzero status with its own
  diagnostic
- **THEN** the signing runner exits with that status
- **AND** it does not append `Traceback` or `CalledProcessError` output.

#### Scenario: Active GitLab signing key advances

- **WHEN** a provider-registered GitLab signing key replaces an unrecoverable
  predecessor for new projection commits and tags
- **THEN** the runner, projection, tag command, OpenSSH agent capability, and
  committed trust anchor select the same public-key fingerprint
- **AND** predecessor anchors remain available to verify immutable history.
