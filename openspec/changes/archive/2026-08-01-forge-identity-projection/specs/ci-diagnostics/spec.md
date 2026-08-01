## MODIFIED Requirements

### Requirement: Provider projection separates source and target authority

Forge publication SHALL project one accepted content history into independent
GitLab and GitHub commit identity domains. GitLab commits SHALL use the selected
GitLab email and trust anchor. GitHub commits SHALL use the selected GitHub email
and trust anchor while preserving the canonical ordered tree history, messages,
dates, and parent topology. Publication SHALL be append-only and SHALL NOT force
update either target. Expected child failures SHALL preserve their exit status
without emitting a Python traceback.

#### Scenario: Accepted source is dev

- **WHEN** the clean canonical checkout is attached to `dev` and its current
  `HEAD` is selected for GitHub projection
- **THEN** GitHub `main` receives the equivalent GitHub-identity history
- **AND** its tip tree and ordered tree history equal the canonical source
- **AND** no canonical ref or existing provider tag is moved or rewritten.

#### Scenario: Different verified emails publish equivalent content

- **WHEN** accepted GitLab source and GitHub require different verified emails
- **THEN** their `main` commit IDs differ
- **AND** their tip tree and ordered tree history are equal
- **AND** every commit verifies under its own Forge email and trust anchor.

#### Scenario: GitHub already contains an admitted projection

- **WHEN** a later canonical GitLab commit is projected
- **THEN** the existing GitHub tip remains an ancestor of the new GitHub tip
- **AND** only the missing canonical descendants are projected
- **AND** the command emits an explicit source-to-provider mapping receipt.

#### Scenario: Target history cannot be mapped uniquely

- **WHEN** the target tip has no unique identity-neutral canonical match
- **THEN** projection fails before any ref update
- **AND** it offers no force or history-rewrite escape.

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
