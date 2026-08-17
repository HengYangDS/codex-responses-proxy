## Context

`uv lock --upgrade --resolution highest --dry-run` reports one stable update:
Pygments 2.20.0 to 2.21.0. The repository also configures both `origin` and
`gitlab-release` with the same GitLab URL, while the publication profile names
the redundant alias as authority.

## Decision

Keep one dependency graph owned by `uv.lock`, one GitLab remote authority named
`origin`, one version owner in `VERSION`, and one contract test for the declared
publication topology. GitLab and GitHub remain independent publication planes;
neither consumes the other.

## Delivery Boundary

The Change owns the source mutation and exact-source proof. Candidate
integration, accepted closeout, provider-native publication, asset parity,
installation, runtime acceptance, and lane retirement remain separately
verified effects after archival.
