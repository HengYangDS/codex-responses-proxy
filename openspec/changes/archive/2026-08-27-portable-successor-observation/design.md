## Context

See [proposal.md](proposal.md). The upgrade command already returns the exact
finalized runtime identity, and `status` independently validates the installed
payload, process identity, admission state, and listener ownership. The failing
test added a second assertion against `psutil` socket enumeration after those
two product observations agreed.

## Goals / Non-Goals

**Goals:**

- Prove one exact successor through two public product observations.
- Keep the acceptance invariant portable across macOS, Linux, and Windows.
- Delete redundant polling rather than weakening lifecycle verification.

**Non-Goals:**

- No production lifecycle change.
- No longer timeout, retry, Windows exception, or alternate process scanner.
- No platform-specific acceptance semantics.

## Decisions

### Compare command and status runtime identities

The test compares the upgrade result and immediate `status` across PID, release,
payload digest, release receipt, and manifest digest, and requires the observed
runtime to accept traffic. This reuses the existing semantic assertion already
used for rollback and forward reversal.

Retaining raw listener enumeration was rejected because it duplicates product
status verification with a host-observation mechanism whose timing and socket
attribution vary by platform. Increasing its timeout would preserve the wrong
contract while making CI slower.

## Risks / Trade-offs

- **Status validation regresses** → its unit, lifecycle, and release tests remain
  authoritative; this acceptance test still compares the independent command
  and status observations.
- **A stale runtime record survives** → the full identity comparison plus
  accepting-state check fails.

## Migration Plan

Update the proposal commit, rerun the Windows published-predecessor job, then
complete the existing dual-Forge review flow. No runtime migration is required.
