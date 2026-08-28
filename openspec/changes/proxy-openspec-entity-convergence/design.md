## Context

OpenSpec 1.10 resolves the repository's `spec-driven` workflow to proposal,
delta specifications, design, and tasks, with `.openspec.yaml` metadata and
`openspec/config.yaml` configuration. The repository also contains historical
README summaries, scope inventories, capability descriptors, and ETHOS
Commitments. Only Commitments still have a current external consumer.

## Goals / Non-Goals

**Goals:**

- Preserve one product-intent authority through official OpenSpec artifacts.
- Delete consumerless files rather than adding a registry, compatibility layer,
  migration shim, or negative-name list.
- Leave externally owned Commitment semantics unchanged until ETHOS supplies a
  replacement authority and migration.

**Non-Goals:**

- Changing Proxy runtime behavior or release assets.
- Reimplementing ETHOS lifecycle semantics in Proxy.
- Rewriting Git history to erase already published files.

## Decisions

### Delete derived summaries and inventories

Archived proposals retain each Change's intent, while Git retains the exact
historical tree. README summaries and scope inventories therefore own no
current invariant. Deleting them is preferable to translating them into a new
carrier.

### Keep normative capability meaning in canonical specifications

Canonical specifications already own requirements and scenarios. TOML
capability descriptors have no runtime consumer and duplicate that meaning, so
they are removed rather than promoted into another registry.

### Use positive carrier admission

An additional carrier is admissible only when all three facts are proven:

1. A current goal cannot be met without the represented invariant.
2. The official schema and existing authorities cannot represent it.
3. The carrier has one owner, one current consumer, and an explicit retirement
   condition, and it replaces rather than parallels another authority.

This criterion lives in the existing repository-organization specification;
there is no separate inventory or blacklist.

### Defer Commitment ownership to ETHOS

Commitments remain because ETHOS currently consumes them for scope, lease,
rebind, and archive recovery. Proxy must not fork that lifecycle. ETHOS owns the
decision to express the contract through an official custom schema or move it
outside the OpenSpec namespace, followed by removal of obsolete carriers.

## Risks / Trade-offs

- Historical convenience files disappear from the current tree → official
  proposals and Git history remain available without creating a second source.
- Commitments remain temporarily non-official OpenSpec neighbours → their
  current consumer and owner are explicit, and no new Commitment mechanism is
  introduced here.

## Migration Plan

1. Remove only the audited consumerless carrier classes.
2. Validate every official OpenSpec artifact strictly.
3. Run repository quality checks that cover layout and documentation.
4. Archive this Change through the OpenSpec command after all tasks pass.
