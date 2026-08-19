## Context

See `proposal.md`. The canonical installation already contains the current
native payload, but its supervisor can still name an install-owned alternate
launcher. The old launcher participates in protocol-v2 handoff, so replacing
the running process by force would create avoidable connection loss.

## Goals / Non-Goals

**Goals:**

- Converge payload, listener, command, and supervisor onto one native identity.
- Make every transition fail closed and retryable from observable local state.
- Prove every public command through both the Python boundary and the released
  native executable.

**Non-Goals:**

- No general legacy-runtime reader, compatibility command, bypass flag, or
  permanent wrapper support.
- No mutation or use of the canonical listener as a validation fixture.
- No change to provider policy or client control planes.

## Decisions

1. **Model the defect as supervisor reconciliation, not legacy support.** The
   alternate launcher is admitted only when the current native payload identity,
   sole listener PID, process generation, and install-root ownership all agree.
   An external or ambiguous launcher remains incompatible.
2. **Use one POSIX-only temporary bridge with an exact retained original.** The
   alternate file is atomically moved to a private backup and replaced by a
   symlink to the canonical executable. Existing protocol-v2 handoff then starts
   the native child without adding a second migration protocol. On failure
   before native commitment, the exact launcher is restored. Windows has no
   admitted historical wrapper shape and rejects this migration path while
   retaining its canonical native lifecycle.
3. **Make the interrupted post-handoff state retryable.** If the native listener
   is already serving while the supervisor still names the bridge, the next
   install proves the same native identity, rebinds supervision, then removes
   the bridge and backup. Declared paths are compared without resolving the
   bridge, so this state cannot be mistaken for a completed rebind.
4. **Separate transaction recovery by state.** A `prepared` journal can be
   removed only when it is canonical and the transaction root contains no other
   entry. A `recovery_required` journal retains the existing candidate,
   rollback, and runtime identity proof.
5. **Use one CLI result model.** Every public command supports `--json`; version
   becomes `{"version": ...}` in machine mode. Expected errors remain bounded,
   nonzero, and traceback-free.
6. **Bind black-box validation to an isolated installation and port.** Release
   tests override payload, state, HOME, user profile, native service identity,
   and listener port. Status discards loopback health unless its PID is the sole
   listener owned by the selected installed executable.

## Risks / Trade-offs

- [Controller failure after native handoff] -> retain the exact bridge backup;
  the next install completes supervisor rebind before payload mutation.
- [Alternate launcher is not the known install-owned shape] -> fail before any
  payload or supervisor mutation and require explicit uninstall.
- [A platform supervisor file is malformed or ambiguous] -> return no configured
  executable and require exact native-listener proof before reinstalling it.
- [Validation accidentally reaches the canonical port] -> reserve a temporary
  loopback port for the complete native command matrix.

## Migration Plan

1. Build the native executable and signed release asset from the accepted tree.
2. Install it into an alternate root and service identity on a temporary port.
3. Prove prepared recovery, alternate-launcher handoff, supervisor rebind,
   uninterrupted long responses, status, doctor, reload, and uninstall.
4. Re-read the canonical runtime and apply the same signed installer without a
   manual signal or service removal.
5. Prove native listener identity, canonical supervisor configuration, absence
   of transaction and alternate-launcher residue, and continuous service.

Rollback remains the existing payload rollback before handoff commitment. An
unknown handoff outcome remains transaction-bound and is never reported as
success.
