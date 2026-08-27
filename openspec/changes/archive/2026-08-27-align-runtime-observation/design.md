## Context

`lifecycle.control.status()` validates the installed payload, runtime payload
identity, process ownership, listener attribution, and accepting state before
returning a runtime object. `doctor` consumed that result but then independently
required a second platform process enumeration to be byte-for-byte current.
Windows can briefly lag that enumeration after a successful native transition,
creating a false failure from two competing interpretations.

The release compatibility fixture had a separate timing defect. Candidate
verification, extraction, and prewarming occur before activation or listener
handoff. A short wait that began at command launch therefore measured artifact
preparation rather than the lifecycle transition and failed on slower hosts.

## Goals / Non-Goals

**Goals:**

- Preserve one owner for admitted runtime identity.
- Start traffic-release observation at a durable transaction boundary.
- Keep exact terminal behavior and residue proof unchanged.

**Non-Goals:**

- No platform exception or runner-specific branch.
- No longer product timeout or weakened successor identity assertion.
- No change to installation, handoff, rollback, or recovery semantics.

## Decisions

### Reuse the status-owned runtime

`doctor` treats a returned accepting runtime as the listener proof. Missing or
non-accepting runtime still fails the listener check. Raw `listener_pids` remains
status evidence for humans and automation, but is not reinterpreted by a second
diagnostic owner.

### Release traffic at activation

The compatibility fixture observes the transaction journal and releases held
requests when the candidate becomes the selected `activated` generation. This
boundary follows materialization and precedes terminal successor proof for both
supported upgrade strategies. The test then requires the command result,
independent status, exact runtime identity, held response bytes, rollback,
forward recovery, uninstall, and zero residue.

The activation wait uses the existing command bound rather than a new timeout:
candidate materialization is part of the same public install command, and the
fixture must not invent a shorter preparation contract.

## Risks / Trade-offs

- **A transaction activates but later fails** → the command, status, rollback,
  and residue assertions remain authoritative and fail the test.
- **A foreign listener exists** → product installation and final status retain
  their exact ownership and payload checks; activation alone never proves
  success.

## Migration Plan

Run focused regressions and native macOS compatibility, then the repository
gates. Archive this change before committing. Hosted Linux and Windows release
compatibility remain required before merge or release.
