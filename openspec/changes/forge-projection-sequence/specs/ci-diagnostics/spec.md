## ADDED Requirements

### Requirement: Explicit continuity maps only successors after its exact base

After uniquely matching the supplied canonical base to the supplied provider
anchor, the projector SHALL map only the ordered successor suffix. Duplicate
identity-neutral fingerprints before either exact cut SHALL NOT participate in
successor ambiguity. Duplicate provider matches after the cut SHALL fail before
commit creation or ref mutation.

#### Scenario: Retired prefixes contain repeated fingerprints

- **WHEN** the explicit base and anchor uniquely identify their sequence positions
- **THEN** earlier repeated fingerprints do not block continuity
- **AND** only successor mappings after both positions are considered.

#### Scenario: A successor fingerprint is ambiguous

- **WHEN** one canonical successor matches multiple provider successors after the cut
- **THEN** projection fails before commit creation or ref mutation.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Explicit continuity maps only successors after its exact base` | `1.1` | `tests/forge/test_continuity.py` |
