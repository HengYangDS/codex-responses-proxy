## Context

The accepted source is newer than version 2.0.33 because it repairs GitLab's
post-sync Python identity. `VERSION` is the sole product version owner, while
the Changelog is the immutable forward release history.

## Decision

Advance to 2.0.34 and publish each Forge independently from the same accepted
source tree. Local release and installation proof remains valid without either
Forge; hosted CI and publication remain separately evidenced effects.

## Rejected Alternatives

| Alternative | Reason |
| --- | --- |
| Reuse 2.0.33 | Would assign changed source to an existing release identity. |
| Rewrite an existing tag or Release | Would destroy immutable failure and publication provenance. |
| Wait for both Forges before local proof | Would couple local product validity to external availability. |
