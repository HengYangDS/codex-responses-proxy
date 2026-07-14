# Release and Change Policy

Status: canonical.

## Change admission

Changes require a scoped regression test, a boundary review, and Python 3.12,
3.13, and 3.14 verification. Documentation must be updated whenever commands,
installation behavior, ownership, or released behavior changes.

## Release identity

`VERSION` is the sole release identifier. A release candidate must satisfy:

- `VERSION`, runtime version lookup, and the dated Changelog heading agree;
- `CHANGELOG.md` begins with `Unreleased`; every published heading maps exactly
  once to a reachable `v<semver>` tag, uses that tag's creation date, and is in
  descending SemVer order. `Unreleased` contains only work after the newest
  reachable tag;
- `scripts/check_release_metadata.py` and the complete CI matrix pass;
- Git tag is exactly `v<VERSION>`;
- claims distinguish structural tests from physical host acceptance.

A source tag records a source version. It is not, on its own, proof of
published artifacts, native-host acceptance, signing, notarization, or an
original-conversation recovery. Those claims require their corresponding,
current evidence and must never be inferred from a Changelog heading.

## GitLab metadata

The display **Project Name** is `Codex DMX Proxy`. The stable repository
**Path** is `codex-dmx-proxy`. Name is prose for people; Path is an external
identifier. A cosmetic display-name correction must not silently migrate clone
URLs, namespace, project ID, default branch, or release history.

## Operational changes

`control.py status` is read-only. `reload` interrupts the local listener and
requires a user-visible warning plus post-replacement identity proof. Route
changes are owned by AIGW whenever its marked provider block is present.
