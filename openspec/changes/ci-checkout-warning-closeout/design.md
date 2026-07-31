## Context

See `proposal.md` for the observed GitHub warning. The runner workspace can
contain a detached commit from the preceding provider projection. During
`actions/checkout`, Git replaces the local `main` branch before checking out the
new remote tip, briefly leaving that detached commit unreachable.

The mitigation must exist before repository checkout, so a checked-in helper
script cannot own the pre-checkout action. The workflow remains the narrow
provider owner while the repository contract test owns its required shape.

## Goals / Non-Goals

**Goals:**

- Preserve only the current valid `HEAD` for the checkout transition.
- Remove the temporary ref on success or failure.
- Keep all Git configuration scopes unchanged.
- Apply the mechanism to every self-hosted checkout in verification and
  release workflows, but not to hosted Windows.

**Non-Goals:**

- A generic Git warning filter or runner cleanup framework.
- A composite action, wrapper script, or compatibility layer.
- Persisting historical runner revisions after the job.

## Decisions

### 1. Use one repository-private non-branch ref

Each self-hosted job updates
`refs/codex-dmx-proxy/runner-checkout-retained` to a valid current `HEAD`
immediately before checkout. Git reachability observes this namespace, while it
does not create a user-visible branch or tag.

A temporary branch was rejected because it enlarges the branch surface.
`advice.detachedHead=false` and `GIT_ADVICE=0` were rejected because they hide
diagnostics and still leave the abandoned-commit warning's first line visible.

### 2. Reconcile stale state before retaining the current revision

If a Git directory exists, the pre-checkout step first deletes any stale copy of
the fixed ref and then recreates it only when `HEAD` validates. A prior canceled
job therefore cannot make an unrelated revision authoritative.

### 3. Cleanup is an explicit always-running step

The post-checkout step uses `if: always()` and deletes the ref only when the
workspace is a Git repository. It runs after a successful or failed checkout
without turning absence of a repository into a new failure.

The provider workflow repeats these two small steps around each self-hosted
checkout because no repository file is available before checkout. Introducing
a remote action or runner-global hook would create a second authority plane for
less code, not less complexity.

## Risks / Trade-offs

- **Hard runner termination can skip cleanup** -> the next pre-checkout step
  deletes stale state before retaining the current valid `HEAD`.
- **A fixed ref could collide inside one workspace** -> GitHub serializes use of
  a runner workspace; each job also reconciles the ref before use.
- **Text-only workflow assertions can drift** -> the contract test parses job
  blocks, verifies ordering and counts, and separately rejects global advice
  suppression.

## Migration Plan

1. Add a failing repository contract for every self-hosted checkout.
2. Add the retain/checkout/always-cleanup sequence to verification and release.
3. Run local provider, release, OpenSpec, quality, coverage, and Python matrix
   gates.
4. Land and project independent provider histories, then require fresh default
   branch CI logs to contain neither the abandoned-commit warning nor another
   prohibited diagnostic.
5. If hosted checkout regresses, revert the workflow commit; no runner-global
   state or runtime payload requires rollback.
