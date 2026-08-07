## Context

The product has one native runtime shape, one provider-portable request path,
and two independent publication planes. Current source still carried an
additional installation model and repeated toolchain projections, increasing
failure surface without serving the terminal product.

## Goals / Non-Goals

**Goals:**

- Keep one executable product surface and one current payload model.
- Fail before mutation when the installed payload is incompatible.
- Keep rollback and recovery exact, current, and receipt-bound.
- Derive repeated versions and matrices from repository-owned sources.
- Prove supported platforms, independent Forges, installation, provider
  switching, original-session continuity, and repository-family closeout.

**Non-Goals:**

- Editing Codex conversation storage or model metadata.
- Configuring a client control plane or IDE product from the proxy.
- Making either Forge an installer dependency.
- Keeping aliases, dual readers, forwarding facades, or generic extension
  points without a current product invariant.

## Decisions

1. Installation has two states: empty target or one verified current native
   listener. Every other state fails before write.
2. The current manifest is the only payload ownership proof. Rollback snapshots
   only the current owned inventory or complete absence.
3. Recovery requires exact candidate, rollback, journal, and live-runtime
   identity. It accepts no paths or bypass flags.
4. Supported supervision adapters use explicit imports so native bundlers see
   every platform implementation without executing the unselected adapter.
5. GitLab and GitHub independently build and publish the same accepted source;
   parity audits identity and bytes without coupling either workflow.
6. Current specifications, tests, docs, and quality rules describe only the
   terminal model. Immutable release evidence is not a product compatibility
   surface.
7. Durable design choices use one Decision Record register and the
   `dr-<sequence>-<description>.md` grammar. OpenSpec remains change authority;
   Decision Records preserve rationale without becoming a parallel spec.

## Failure Boundaries

| Boundary | Failure | Required behavior |
| --- | --- | --- |
| Build | Adapter omitted | Release gate fails |
| Install | Payload incompatible | No mutation; explicit removal action |
| Handoff | Outcome unknown | Retain candidate and rollback for recovery |
| Recovery | Identity mismatch | Preserve transaction; fail closed |
| Forge | One plane unavailable | Other plane remains independently usable |
| Provider | One route unavailable | Other routes remain usable |
| Closeout | Owner residue remains | No completion claim |

## Verification

- Focused tests for current-only installation, rollback, recovery, and adapter
  assembly.
- Quick, quality, Python 3.12/3.13/3.14, native release, and strict OpenSpec.
- Statement, branch, and package coverage each strictly above 95%.
- Native macOS installation plus hosted Linux and Windows executable proof.
- Independent GitLab and GitHub releases with byte-identical assets.
- DMXAPI -> UCloud -> AIHubMix -> DMXAPI requests with `store=false`.
- Successful replies in the exact original Codex conversation.
- Repository-family and process audit with no owner residue.
