## Context

See [proposal.md](proposal.md) for the failure. The prior implementation let
three mechanisms influence upgrade convergence: the transaction journal, the
listener handoff protocol, and the platform supervisor. Rebinding the supervisor
before terminal listener ownership was known made the supervisor an accidental
second authority. A later control-layer compensation then attempted to repair
that ordering after the transaction had already closed.

## Goals / Non-Goals

**Goals:**

- Give every lifecycle phase one state authority and one transition owner.
- Keep rollback and recovery possible until terminal listener and supervisor
  identities are both proved.
- Make supervisor binding a deterministic projection of the proved terminal
  payload.
- Delete compensation, timeout, retry, marker, and predecessor-specific paths
  that exist only to mask the authority error.
- Prove the model first on a real Linux user-systemd host using a signed
  published predecessor and continuous ordinary and streaming requests.

**Non-Goals:**

- Adapting product semantics to a damaged VM or runner.
- Claiming macOS or Windows acceptance from unit tests or Linux evidence.
- Adding a second transaction, compatibility protocol, or supervisor-owned
  generation selector.
- Changing provider, credential, client, or publication behavior.

## Decisions

### Existing authorities carry the design by default

The change adds no product-state carrier beyond the official OpenSpec artifacts
and the existing ETHOS Commitment required by repository governance. Before any
new file, schema, helper, abstraction, state, or compatibility path is admitted,
the design must establish all three conditions:

1. The required behavior cannot be expressed by an official OpenSpec artifact.
2. It cannot be expressed by simplifying or extending an existing authority.
3. It becomes the sole owner of one necessary invariant and permits the entity
   it replaces to be removed.

Failure to establish any condition means the existing authority must be reused,
merged, simplified, or deleted instead. Convenience and speculative reuse do
not establish necessity.

### The deployment phase has one authority

While an upgrade is incomplete, the transaction journal owns recovery state:
the admitted candidate, predecessor rollback inventory, handoff outcome, and
pending supervisor binding. After terminal convergence, the active-generation
selector becomes the sole steady-state authority. The supervisor never becomes
a third state source.

Alternatives rejected: inferring state from service-manager registration,
process presence, marker files, elapsed time, or retry count. Those observations
are proof inputs, not authorities.

### Listener ownership precedes supervisor projection

The transition order is:

```text
materialize
→ activate
→ listener handoff / generation replacement
→ prove terminal admission owner
→ bind and prove supervisor
→ prune obsolete generation
→ close transaction
```

This order ensures a service manager is only asked to preserve a generation
that has already proved terminal admission ownership. A failed supervisor bind
therefore leaves one serving successor plus a recoverable transaction, rather
than forcing a second handoff or an ambiguous rollback.

### Recovery closes the same transaction

`recover` receives one narrow terminal-binding operation. It reuses the proved
handoff result, binds the correct supervisor, proves configured and running
identity, then prunes and closes. Failure preserves the journal, candidate, and
rollback bytes. Rollback similarly proves the restored predecessor supervisor
before closure.

The rejected alternative is a control-layer compensation after transaction
closure. That path lacked the rollback inventory and duplicated lifecycle
ownership.

### Platform adapters prove one common contract

Each adapter may use native mechanisms, but success has the same meaning:
service identity, configured executable, running watchdog identity, and terminal
payload all agree. Linux uses `daemon-reload`, exact-service enable/restart,
`MainPID` observation, and watchdog identity proof. macOS and Windows require
separate real-host evidence before cross-platform acceptance is claimed.

## Risks / Trade-offs

- A supervisor bind can fail after successful handoff. Mitigation: keep the
  transaction and both payload inventories intact; recover without replaying
  handoff.
- A damaged service-manager host can produce misleading failures. Mitigation:
  restore a clean validation host and do not weaken product semantics.
- Unit tests can prove ordering but not native service behavior. Mitigation:
  require published-predecessor real-host acceptance before completion.
- Platform adapters may still differ semantically. Mitigation: audit each
  adapter against the common proof contract and retain platform-specific
  acceptance gaps explicitly.

## Migration Plan

1. Preserve the published `3.1.2` predecessor and verify its signature.
2. Build a candidate from the current source with the locked toolchain.
3. Upgrade under continuous ordinary and streaming requests on a clean Linux
   user-systemd host.
4. Prove listener, selector, transaction, service registration, `MainPID`,
   executable identity, rollback, recovery, repeat upgrade, and zero residue.
5. Run affected repository gates once after focused evidence is green.
6. Repeat the same contract on macOS and Windows before claiming cross-platform
   completion.
