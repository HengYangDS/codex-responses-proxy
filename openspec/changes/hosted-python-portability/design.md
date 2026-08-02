# Design: Hosted Python portability

## Authority

`requires-python >=3.12` and the documented 3.12, 3.13, and 3.14 matrix own the
product support boundary. Forge workflows are projections of those three minor
release lines, not owners of a universal patch build.

## Resolution

GitHub `setup-python` receives `3.12`, `3.13`, or `3.14`; GitLab official Python
images receive the same line identifiers. Each official supply surface selects
a stable patch actually published for that runner platform. Repository contract
tests reject `3.12.x`, `3.13.x`, or `3.14.x` literals in hosted CI files, so a
future patch refresh cannot recreate cross-platform drift.

## Boundaries

This does not loosen the supported interpreter matrix, introduce arbitrary
`latest`, change local runtime selection, or reduce reproducibility of source,
action revisions, quality dependencies, release assets, or signed Git objects.
