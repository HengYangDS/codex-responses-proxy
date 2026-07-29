# Release and Change Policy

Status: canonical.

## Change admission

Changes require scoped regression tests, boundary review, and candidate
verification on Python 3.12, 3.13, and 3.14. Documentation must change with
commands, ownership, installation, lifecycle, evidence, or released behavior.
A local green gate proves only the local candidate; it does not prove either
Forge publication or an installed runtime.

## Release identity

`VERSION` is the release-train identifier. Before a tag exists, it must be
strictly newer than the latest release and its material remains under
`Unreleased`. A release commit moves that material to a dated heading and is
tagged as exact `v<VERSION>` on the same UTC date. A release candidate must
satisfy all of the following:

- `VERSION`, runtime version lookup, and the dated Changelog heading agree;
- `CHANGELOG.md` starts with one `Unreleased` heading and released headings are
  descending, date-correct, and in one-to-one correspondence with reachable
  provider-native tags;
- repository metadata, quality, coverage, and the complete platform matrix pass;
- the tag is a signed annotated tag that directly identifies the release commit;
- claims distinguish source structure, Forge publication, local installation,
  physical host acceptance, and original-task recovery.

A tag is source identity, not publication proof by itself. No candidate may be
installed before both Forge planes have completed their signed tag, required CI,
and formal Release record.

## Independent Forge publication proof

GitLab and GitHub are equal, independent authority planes. Each owns its commit
history, signed tag object, CI execution, and Release record. GitHub is projected
from the canonical GitLab tree through a fresh isolated clone, but its commits
and tags retain GitHub-native identity.

`scripts/verify-publication-proof.py` is the in-repository, read-only verifier.
It fetches each exact tag into isolation, verifies each provider signature under
its own external anchor, observes the policy-required hosted jobs and Release
record, and requires the two tags to bind the same source tree. Its JSON is
audit evidence only. Installation repeats live verification in the same process;
no serialized document can be converted back into installation authority.

The source-side installer independently requires a clean checkout whose `HEAD`
is the exact signed annotated `v<VERSION>` tag. It reads payload bytes from Git
objects, never from an arbitrary working-tree stage. `platform_adapters.release_source`
returns an opaque one-use capability binding source identity, publication proof,
payload blobs and modes, aggregate serving identity, receipt, and sidecar.

## Installation transaction

Every payload mutation is owned by source-side `install.py`. The installer
consumes the release capability into one private transaction that owns the
candidate projection, rollback snapshot, canonical receipt, manifest,
installed-release state, and recovery hold. It refuses downgrades and same-version
replays. It finalizes only after the accepting listener proves release,
aggregate serving-payload digest, release-receipt digest, and manifest digest.

Failure before a proven terminal state restores the exact previous owned
projection. If a committed handoff result is unknown, the transaction is kept as
`recovery_required`; neither success nor rollback may be inferred. Installed
control exposes no arbitrary stage-path upgrade and no controller-only partial
apply. Release archives are not installation sources because they cannot carry
the signed annotated tag object and its verified publication chain.

Route changes remain owned by AIGW whenever its marked provider block is present.

## Lifecycle operations

`control.py status` and `governance.py` are read-only. Installed-control `reload`
is same-payload only and requires a user-visible warning plus post-operation
identity proof. It prepares a non-accepting child, stops the old accept loop
before `COMMIT`, and requires `SERVING` proof by PID, transaction, release,
aggregate serving-payload digest, release-receipt digest, and manifest digest
before `FINALIZE`. Accepted handlers drain to zero or the bounded lease.
Pre-finalize failure confirms child exit before old admission resumes; an
unconfirmed abort fails closed.

Replacing payload bytes is a source-side install operation. For a current
protocol-v2 listener, source-side deployment commits the admitted release
transaction and uses the same handoff transport and identity proof. A one-time
legacy replacement requires explicit `--allow-legacy-bootstrap`, installed
manifest integrity, exactly one verified PID, and a bounded zero-active quiet
window. `--force-legacy-bootstrap` adds separate interruption authorization; it
is unavailable to `reload`, rejected without the allow flag, and never applies
to a current protocol-v2 listener.

## Reliability observation and incident boundary

`control.py status --json` is the secret-free source of listener-local counters.
`scripts/observe-reliability.py` evaluates a supplied snapshot and optional
explicit baseline file; it does not contact the listener, mutate configuration,
retain request or response material, or perform lifecycle control.

Counters are comparable only when release, startup-frozen aggregate
serving-payload digest, and monotonic uptime identify the same running payload.
A first snapshot, restart, or payload change starts a new observation window;
lifetime counters and `last_failure` are not reclassified as new incidents.
Payload-integrity failure, missing or multiple verified listeners, local stream
failures, pre-content exhaustion, and local queue timeouts are immediate local
incidents. Drain rejections remain a separate local class: approved maintenance
may classify them as `observe`, never as upstream failure.

Upstream `empty_response`, retryable 5xx, `response_failed`, and the exact input-
variant validation class are evaluated independently. One or two new events in
a comparable window require observation; three or more require an incident.
These gates prove only the stated runtime evidence. Historical Codex task
recovery requires a separate acceptance result from that exact task after a
released runtime is serving.
