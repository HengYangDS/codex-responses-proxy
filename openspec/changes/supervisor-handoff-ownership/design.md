## Context

See `proposal.md`. Payload projection, native supervision, and listener handoff
are one installation transaction, but the failed release candidate delegated
supervisor installation to the successor handoff child. On systemd and Task
Scheduler that child can therefore restart the service that owns itself before
it sends the final protocol acknowledgement.

## Goals / Non-Goals

**Goals:**

- Give supervisor mutation one source-side owner.
- Preserve the listener handoff protocol and uninterrupted request semantics.
- Restore the prior payload and supervisor together after a proved rollback.
- Prove native behavior on macOS, Linux, and hosted Windows.

**Non-Goals:**

- No new supervisor abstraction, compatibility mode, or background process.
- No provider, credential, client projection, or Codex state changes.
- No reliance on Forge availability during local installation.

## Decisions

1. **The installer owns supervisor rebinding.** After committing the verified
   payload, it installs the platform-native supervisor and reads the resulting
   declaration back before asking the listener to hand off. This preserves one
   transaction owner and prevents the successor from replacing itself.
2. **The handoff child owns listener capability only.** Its finalization callback
   is removed rather than retained as an optional extension point. A dormant
   callback would preserve the incorrect ownership model and invite a parallel
   mutation path.
3. **Rollback restores supervision after restoring bytes.** A proved handoff
   failure rolls back the payload, then installs the supervisor again from the
   restored path. An unknown listener outcome keeps the candidate transaction
   intact because replacing supervision with the predecessor would contradict
   the still-possible successor state.
4. **Configured executable proof compares normalized declared paths.** The
   installer accepts semantically identical platform paths but does not resolve
   arbitrary launchers or use process-path heuristics at this boundary.
5. **Cross-platform acceptance is layered.** Focused tests prove order and
   rollback; the complete Python matrix proves supported interpreters; native
   macOS and Linux release flows prove frozen products; hosted Windows proves
   Task Scheduler and handoff behavior on a Windows kernel.

Rejected alternatives:

- Finalize supervision inside the child: self-replacement caused the incident.
- Restart supervision after handoff: leaves a committed listener with stale
  recovery ownership and creates another interruption window.
- Skip supervisor proof: file projection alone does not prove native-manager
  configuration.
- Add a portable supervisor framework: it would create a second lifecycle owner.

## Risks / Trade-offs

- [Supervisor install succeeds but read-back differs] → roll back before handoff
  and restore predecessor supervision.
- [Controller loses certainty after handoff starts] → retain the existing
  recovery-required transaction and do not claim rollback.
- [A platform path has an equivalent spelling] → compare normalized declared
  paths without following an alternate launcher.
- [Hosted Windows is unavailable] → local completion remains explicitly
  unproved; macOS or Linux success does not substitute for Windows acceptance.

## Migration Plan

1. Verify focused order, rollback, and handoff-child tests.
2. Pass quick, quality, Python 3.12/3.13/3.14, macOS native release, and Linux
   native release from the exact source tree.
3. Publish the signed proposal commit and require hosted Windows native release
   acceptance.
4. Delete the failed `v2.0.53` tag from both Forges, archive this completed
   change, and mint one replacement signed release object from the accepted
   source.
5. Install the verified release asset and prove the canonical service, listener,
   transactions, and host projections are clean.
