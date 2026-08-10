# Tasks

## Contract and repair

- [x] 1.1 Reproduce the Forge failure with a real repository lacking `candidate/dev`.
- [x] 1.2 Select the first available integration base while preserving local candidate priority.
- [x] 1.3 Advance VERSION, Changelog, and README examples to `2.0.21`.

## Verification

- [x] 2.1 Pass focused commit policy, metadata, OpenSpec, and presentation tests.
- [x] 2.2 Pass quick, quality, Python 3.12/3.13/3.14, and native release gates.
- [x] 2.3 Prepare exact-HEAD proof, archive, and land for the governed source transition.

## Post-archive delivery contract

- [x] 3.1 Preserve v2.0.20 tags and failed runs as immutable evidence.
- [x] 3.2 Require independent GitLab and GitHub v2.0.21 publication from one accepted tree.
- [x] 3.3 Keep trusted installation, runtime acceptance, and lane retirement as fresh external transitions.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `ci-diagnostics:Commit grammar follows the checkout's available integration boundary` | `1.1` | `test_commit_subjects_use_remote_main_when_candidate_is_local_only` |
| `ci-diagnostics:Commit grammar follows the checkout's available integration boundary` | `1.2` | `tools/quality/commits.py` |
| `ci-diagnostics:Commit grammar follows the checkout's available integration boundary` | `2.2` | `locked-local-verification-graph` |

Hosted CI, Releases, installation, runtime behavior, and repository-family
retirement are not asserted by OpenSpec archival.
