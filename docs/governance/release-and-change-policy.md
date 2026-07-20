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

`control.py status` and `governance.py` are read-only. `reload` and staged
upgrade require a user-visible warning and a post-operation identity proof.
They first wait for a bounded zero-active quiet window without closing Responses
admission. They then close admission, allow already admitted work to finish, and
may proceed only after loopback health reports `draining=true` with
`active_responses=0`.

A timeout restores admission without committing a staged payload; failure to
find the quiet window starts no drain; a bounded listener lease also fails open
if the controller disappears. A controller-only apply is not a reload or
upgrade: it requires exactly one verified listener serving normal admission and
proves every listener, watchdog, version, and support file byte-identical to the
verified live payload. It transactionally swaps only `control.py` and the
manifest, preserves route state and logs, and does not drain, restart, or
interrupt Responses traffic.
Route changes are owned by AIGW whenever its marked provider block is
present.

## Reliability observation and incident boundary

`control.py status --json` is the listener-local, secret-free source of raw
runtime counters. `scripts/observe-reliability.py` is the corresponding
source-side evaluator: it accepts a supplied snapshot and an optional explicit
baseline state file, but does not call the listener, mutate configuration,
retain request/response material, or perform lifecycle control.

The evaluator compares counters only when release, loaded source digest, and
monotonic uptime prove the same running payload. A first snapshot, a restart,
or a payload change begins a new observation window; lifetime counters and
`last_failure` must not be reclassified as a new incident. Payload-integrity
failure, missing/multiple verified listeners, local stream failures,
pre-content stream exhaustion, and local queue timeouts are immediate local
incidents. Drain rejections remain a separate local class: an approved
maintenance observation may classify them as `observe`, never as an upstream
failure. Upstream `empty_response`, retryable 5xx, and `response_failed` are
classified independently; one or two events in a comparable window require
observation, while three or more require an upstream incident. The policy is
deliberately bounded and must remain covered by deterministic tests.

For a one-time upgrade from a listener that predates drain control, lifecycle
control requires explicit operator authorization and may use only its
verified-PID, two-sample five-second idle-window compatibility gate. It must
refuse on any activity, health loss, timeout, or PID change, and it is not an
alternative for listeners that support atomic drain.

An emergency forced legacy bootstrap is an interruption, not a drain. It needs
separate operator authorization, manifest integrity, and exactly one verified
listener; it is unavailable to ordinary reload and must disappear from use after
the first drain-capable listener has started.
