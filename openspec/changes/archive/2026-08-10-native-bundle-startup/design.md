# Design

## Decision

PyInstaller remains the native freezer but uses its directory mode exclusively.
The directory is the payload: all regular files below it plus `providers.toml`
are enumerated, hashed, signed through the existing asset chain, staged, and
verified. The executable keeps the stable installed path
`bin/codex-responses-proxy`; adjacent frozen dependencies retain their relative
paths below `bin/`.

The installer runs the staged executable's bounded `version` probe before the
payload transaction commits. This pays any platform provenance cost outside the
handoff window. A failed probe leaves the installed projection untouched.

## Ownership

| Concern | Semantic owner |
| --- | --- |
| Native bundle construction | `noxfile.py` release session |
| Reproducible archive inventory | `tools.release.assets` |
| Signed archive admission | `lifecycle.artifact` |
| Runtime file identity | `service.inventory` |
| Candidate validation and prewarm | `lifecycle.candidate` |
| Commit, rollback, and recovery | Existing lifecycle transaction modules |

No module translates between old and new payload shapes. Manifest schema and
tests move directly to the bundle contract.

## Failure boundaries

1. An unsafe, duplicate, missing, symbolic-link, or unmanifested bundle member
   fails before candidate materialization.
2. A digest, mode, or executable-path mismatch fails before payload commit.
3. A prewarm failure removes the staging candidate and does not contact the
   current listener.
4. Once committed, existing exact manifest, handoff, rollback, and recovery
   checks apply to the complete bundle.

## Verification

TDD first pins recursive inventory, archive reproducibility, prewarm ordering,
rollback, no-Python execution, and real handoff startup. The complete locked
quick, quality, Python 3.12-3.14, and release graph then proves the final tree.
