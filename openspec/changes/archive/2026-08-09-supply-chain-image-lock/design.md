## Decision

`.python-versions` remains the supported-version SSOT. `.gitlab-ci.yml` owns the
digest-bound registry references required by GitLab. Contract tests parse those references
and validate shape and semantic agreement rather than repeating concrete tags or
digests.

| Concern | Owner |
|---|---|
| Supported Python minors | `.python-versions` |
| GitLab image artifacts | `.gitlab-ci.yml` |
| Consistency rule | repository contract test |

A dedicated updater is not introduced: the existing supply-chain refresh flow
updates the two owners atomically.
