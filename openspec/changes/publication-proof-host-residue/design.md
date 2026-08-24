## Context

Provider adapters validate Forge-specific workflow and required-job semantics.
The evaluator validates the provider-neutral release identity. Today those two
boundaries disagree about the `ci.jobs` field: adapters emit it after checking
it, while the evaluator rejects it as unknown.

On macOS, current controlled reproduction shows that `launchctl bootstrap`
followed by exact-target `bootout` creates no persistent override. The host's
existing suffixed override records therefore belong to older lifecycle
generations and must not be misrepresented as a defect in current teardown.

## Goals / Non-Goals

**Goals:**

- Keep provider-specific job validation at the provider boundary.
- Give the evaluator one closed, provider-neutral evidence schema.
- Prove each current isolated lifecycle leaves no net launchd projection.
- Prove the canonical service label, plist, process, and listener are unchanged.
- Keep historical exact-label repair separate from ordinary uninstall.

**Non-Goals:**

- Weakening unknown-field rejection.
- Moving Forge-specific API semantics into the evaluator.
- Prefix-based launchd cleanup or reset of the user launchd domain.
- Changing request handling, provider policy, or formal runtime configuration.

## Decisions

### Normalize at the composition boundary

The provider adapters remain responsible for proving all required jobs. The
verification orchestrator selects the evaluator's canonical `ci` fields from
that validated evidence before merging it with Git evidence. The evaluator
continues to reject every unknown field.

This keeps one schema owner and avoids making provider job names part of the
cross-Forge comparison model.

### Separate current lifecycle proof from historical host migration

macOS teardown addresses one fully qualified service target, proves process and
registration absence, and removes its plist. Native acceptance snapshots the
exact registered-label, override, and plist sets before and after successful
and interrupted lifecycles; equality proves that current code adds no residue.

Historical override records are not removed by adding an unproved command to
normal uninstall. They require a separately reviewed host migration over an
explicit list of obsolete labels. That migration must not enumerate a prefix,
touch the canonical label, or become permanent compatibility logic.

The canonical service is protected by tests that snapshot its exact projection
and listener independently from the isolated identity.

## Risks / Trade-offs

- Normalization could hide an unvalidated job map. Mitigation: adapters validate
  the complete required-job set before returning evidence, and a regression
  sends real adapter-shaped output through the full verifier.
- Launchd behavior differs by OS release. Mitigation: native acceptance compares
  the real host projection before and after current lifecycle execution.
- Cleanup could target the public service. Mitigation: alternate install roots
  retain deterministic suffix identities and all mutation is exact-label.

## Migration Plan

1. Add failing publication and macOS teardown regressions.
2. Implement the smallest normalization change and strengthen native no-growth
   acceptance without changing current teardown semantics.
3. Run focused tests, then the complete locked quality and Python matrix once.
4. Run controlled native lifecycle proof and verify both zero net residue and
   an unchanged formal service.
5. Re-run the live `v3.0.3` dual-Forge verifier and retain its immutable receipt.
