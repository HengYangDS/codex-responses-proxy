# Release and Change Policy

Status: canonical.

## Change admission

Changes require a scoped regression test, a boundary review, and Python 3.12,
3.13, and 3.14 verification. Documentation must be updated whenever commands,
installation behavior, ownership, or released behavior changes.

## Release identity

`VERSION` is the active release-train identifier. Before a tag exists, it must
be strictly newer than the latest released version and the work belongs under
`Unreleased`. A release commit moves that material to a dated heading and is
tagged as `v<VERSION>`. A release candidate must satisfy:

- `VERSION`, runtime version lookup, and the dated Changelog heading agree;
- `CHANGELOG.md` begins with `Unreleased`; every locally published heading maps
  exactly once to a reachable provider-native `v<semver>` tag, uses that tag's
  creation date, and is in descending SemVer order. `Unreleased` contains only
  work after the newest reachable tag;
- `scripts/check_release_metadata.py` and the complete CI matrix pass;
- Git tag is exactly `v<VERSION>`;
- claims distinguish structural tests from physical host acceptance.

A source tag records a source version. It is not, on its own, proof of
published artifacts, native-host acceptance, signing, notarization, or an
original-conversation recovery. Those claims require their corresponding,
current evidence and must never be inferred from a Changelog heading.

## Independent forge operation

GitLab and GitHub are equal, independent forge planes. Each owns its commit
history, signed tags, CI execution, and release record. `scripts/project-github-
forge.sh` projects the canonical GitLab branch through a fresh isolated clone
with the GitHub identity; it never copies, overwrites, or regenerates tags.
When a version is released on both planes, the two same-named tags are separate
provider provenance objects and must verify against their respective trust
anchors.

The canonical release sequence is explicit: `tag-gitlab-release.sh` creates and
verifies the GitLab-native tag with the GitLab identity and signer; after its
pipeline evidence, `tag-github-release.sh` creates and verifies the GitHub-native
tag in the projected identity history. No ambient Git configuration may select a
provider signer implicitly.

## GitLab metadata

The display **Project Name** is `Codex DMX Proxy`. The stable repository
**Path** is `codex-dmx-proxy`. Name is prose for people; Path is an external
identifier. A cosmetic display-name correction must not silently migrate clone
URLs, namespace, project ID, default branch, or release history.

## Operational changes

`control.py status` and `governance.py` are read-only. `reload` interrupts the
local listener only after loopback health proves it is drained, and requires a
user-visible warning plus post-replacement identity proof. An explicit
`--force-active-responses` bypasses only the drain gate and requires separate
operator authorization. Route changes are owned by AIGW whenever its marked
provider block is present.
