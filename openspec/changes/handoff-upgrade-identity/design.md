## Context

The installed listener freezes the identity of the bytes it loaded. During an
upgrade, however, `install.py` first commits a new projection and then asks the
old listener to transfer its socket to a child that will load those new bytes.
The current preflight incorrectly derives the expected disk identity through
the old process's frozen callbacks, so a valid version change is rejected.

## Goals / Non-Goals

**Goals:**

- Verify the exact successor bytes already committed on disk.
- Keep request preparation and child startup fail closed.
- Recover the existing committed transaction without guessing or direct journal
  edits.

**Non-Goals:**

- Relaxing signed-source admission or dual-Forge publication proof.
- Letting installed control admit arbitrary payloads.
- Editing Codex history, model metadata, or AIGW configuration.

## Decisions

The handoff owner will parse and validate the canonical payload manifest from
the installed root, verify the complete manifest-owned file set, and compare
its release, serving digest, receipt digest, and manifest digest with the
controller request. Frozen callbacks remain the current-process runtime proof,
not the successor-disk proof.

Recovery is a source-side, publication-gated rollback of the existing
`recovery_required` transaction. It validates the canonical journal and exact
rollback snapshot, requires the accepting listener to report that same prior
runtime identity and be the sole PID bound to the installed entrypoint,
restores the prior projection, and removes the transaction
only after restoration succeeds. The newer release then starts a fresh admitted
transaction. If the still-running protocol-v2 listener cannot advance across
versions, a separate `--force-v2-bootstrap` authorization binds that one idle
accepting PID to the exact installed entrypoint before interruption, and proves
either the successor or the restored prior runtime.

## Risks / Trade-offs

- **Disk mutation between validation and child load** -> the child independently
  freezes and echoes the same identity before COMMIT.
- **Ambiguous recovery state** -> recovery accepts only one canonical journal,
  intact rollback, and a live accepting listener matching that rollback;
  every other state remains blocked.
- **More manifest I/O in the old process** -> bounded to one local handoff
  request and the small declared runtime inventory.

## Migration Plan

1. Prove the corrected behavior with unit and real cross-version integration
   tests.
2. Publish the fix as a new release.
3. From the exact released source, restore the retained `1.0.36` rollback
   snapshot with `--rollback-recovery`, then install `1.0.37` through a fresh
   admitted transaction and the authorized v2 bootstrap.
4. If rollback or listener binding fails, preserve the transaction or restored
   prior runtime respectively and do not claim installation success.

## Open Questions

None.
