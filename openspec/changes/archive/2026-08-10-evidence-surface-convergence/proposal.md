## Why

`evidence/parity/` is an empty generic-adopter placeholder. The product does
not declare that evidence family, and its real cross-Forge equality proof is
owned by the Forge auditor. Retaining the directory creates a third,
non-authoritative meaning of parity.

## What Changes

- Remove the unused generic parity placeholder.
- Admit only the project-owned `claims` and `chronicle` evidence roots.
- Add a positive repository gate that reports any new top-level evidence root.

## Capabilities

### New Capabilities

- `evidence-layout`: subject=durable project evidence ownership; reuse=new;
  change=add; facet:lifecycle=validation; facet:surface=quality,evidence;
  facet:authority=source,test,docs.

### Modified Capabilities

- None.

## Out of Scope

- Changing historical claims or chronicles.
- Moving dual-Forge verification out of `tools/forge/audit.py`.
- Changing ETHOS generic adopter-parity semantics.

## Impact

The repository loses one empty semantic surface and gains one small,
repository-native layout check in the existing quality command.
