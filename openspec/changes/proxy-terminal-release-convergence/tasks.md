## 1. Authority model

- [x] 1.1 Reproduce the Linux published-predecessor failure and trace listener,
      transaction, selector, and supervisor ownership through the failing
      boundary.
- [x] 1.2 Specify one deployment authority, one steady-state authority, and the
      terminal transition order in the runtime-upgrade delta and design.
- [x] 1.3 Add regressions proving supervisor binding occurs after terminal
      listener ownership and before pruning or transaction closure.

## 2. Root-cause repair

- [x] 2.1 Remove pre-handoff supervisor replacement and post-closure control
      compensation; verify focused lifecycle tests reject the old ordering.
- [x] 2.2 Make recovery bind and prove the terminal supervisor while retaining
      the journal and payload inventories on failure; verify idempotent retry
      does not replay handoff.
- [x] 2.3 Make Linux user-systemd replacement reload, enable, restart, observe
      `MainPID`, and prove exact watchdog identity.

## 3. Local verification

- [x] 3.1 Run the focused lifecycle and supervision test set.
- [x] 3.2 Run strict OpenSpec validation after restoring canonical-spec
      projection ownership to archive/apply.
- [x] 3.3 Run the locked quick repository gate with the repository uv and Python
      toolchain.

## 4. Native platform acceptance

- [ ] 4.1 Use one clean amd64 Ubuntu user-systemd execution environment; runner
      registration is infrastructure maintenance, not product acceptance.
- [ ] 4.2 Re-verify the published `3.1.2` predecessor signature and build a
      candidate from this exact source tree with the locked toolchain.
- [ ] 4.3 Upgrade from `3.1.2` under continuous ordinary and streaming requests;
      prove zero admitted-request loss, successor listener identity, absent
      transaction residue, matching selector, systemd `MainPID`, executable,
      and watchdog identity.
- [ ] 4.4 Prove rollback, recover, and a subsequent upgrade on the same clean
      contract, then prove zero owned service, process, and file residue.
- [ ] 4.5 Prove the same published-predecessor upgrade, bidirectional rollback,
      recover, uninstall, reinstall, and zero-residue contract on macOS without
      changing the formal `3.1.2` service.

## 5. Terminal verification

- [ ] 5.1 Audit macOS and Windows adapters against the same terminal supervisor
      contract; record and repair only proved semantic gaps.
- [ ] 5.2 Run the full affected quality, test, build, release, installation, and
      native acceptance gates once all focused regressions are green.
- [ ] 5.3 Delete obsolete compensation and compatibility paths with no terminal
      consumer, then verify the final diff contains one lifecycle meaning.
- [ ] 5.4 Archive the Change only after current receipts prove every completed
      platform and explicitly leave any unproved platform incomplete.

## Requirement To Task To Proof

| Requirement                                                               | Tasks       | Proof                                                 |
| ------------------------------------------------------------------------- | ----------- | ----------------------------------------------------- |
| `runtime-upgrade:Native supervision projects the terminal generation`     | `1.1`-`5.4` | focused lifecycle tests; native platform receipts     |
| `runtime-upgrade:Transactional handoff is the sole generation transition` | `1.1`-`5.4` | transaction/recovery tests; published-predecessor E2E |
