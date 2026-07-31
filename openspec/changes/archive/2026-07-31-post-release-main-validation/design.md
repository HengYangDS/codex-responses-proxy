## Context

The metadata checker already owns three valid modes: exact-tag validation, ordinary provider validation, and pending-release preparation. The GitLab projection collapsed the latter two into one branch fallback, which became invalid as soon as main advanced after publishing the current `VERSION`.

## Decisions

1. Keep release semantics in `check_release_metadata.py`; the CI projection only observes ref state and selects one existing mode.
2. Preserve exact tag validation as the first branch.
3. For untagged commits, test the locally fetched exact `refs/tags/v$(cat VERSION)` ref. An existing tag selects ordinary provider validation; an absent tag selects `--prepare-release`.
4. Extend the current release-contract test rather than create another shell wrapper or configuration owner.

## Risks / Trade-offs

- A shallow or stale tag namespace would choose the wrong mode. The job already requires full history and force-fetches tags with pruning before dispatch.
- Broad tag-name matching could admit an unrelated ref. The dispatch verifies the exact fully qualified tag derived from the strictly validated `VERSION` owner.

## Verification

Run the focused release-contract test first, then release metadata, Markdown, strict OpenSpec validation, the Python 3.12/3.13/3.14 matrix, the canonical quality gate, exact-HEAD ETHOS proof, and hosted GitLab/GitHub main verification. Scan captured hosted logs for forbidden diagnostics separately.
