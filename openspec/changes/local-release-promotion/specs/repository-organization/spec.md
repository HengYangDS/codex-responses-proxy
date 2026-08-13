## MODIFIED Requirements

### Requirement: Governed release-branch convergence

The repository SHALL advance local release `main` from accepted `dev` only
through the adopted package-only ETHOS closeout command. Proxy source SHALL NOT
define a second release-root mutation command. The transition SHALL be local,
exact-head guarded, and independent of both Forge publication planes.

#### Scenario: Candidate is proved

- **WHEN** `candidate/dev` and accepted `dev` identify the same clean, proved
  commit and local `main` is its ancestor
- **THEN** ETHOS closeout MAY fast-forward `main` by exact compare-and-swap
- **AND** no remote ref, tag, Release, asset, client, or Codex session state is
  changed.

#### Scenario: Local transition facts drift

- **WHEN** the observed head, proof, branch role, candidate, accepted root, or
  worktree cleanliness changes before apply
- **THEN** closeout SHALL fail before `main` moves.

#### Scenario: Direct main update is attempted

- **WHEN** direct Git mutation bypasses ETHOS
- **THEN** admission SHALL fail closed and the protected ref SHALL remain
  unchanged.

#### Scenario: A second product-owned transition is proposed

- **WHEN** Proxy code attempts to implement the same local `dev` to `main`
  mutation
- **THEN** repository review SHALL reject it as a duplicate lifecycle owner.
