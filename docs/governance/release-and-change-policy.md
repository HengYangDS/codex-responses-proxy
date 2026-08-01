# Release and Change Policy

Status: canonical.

## Change admission

Changes require scoped regression tests, boundary review, and candidate
verification on Python 3.12, 3.13, and 3.14. Documentation must change with
commands, ownership, installation, lifecycle, evidence, or released behavior.
A local green gate proves only the local candidate; it does not prove either
Forge publication or an installed runtime.

Canonical test jobs treat Python warnings and unhandled tracebacks as failures.
Expected peer disconnects in loopback integration tests are handled at the
fixture boundary, while production HTTP responses remain explicitly closed.
Compilation writes bytecode only to an isolated temporary prefix, and quality
checks do not retain a Ruff cache in the checkout. A bare Ruff or ty command is
resolved to the first PATH candidate with the exact repository-required
version, so an outer runner's virtual environment cannot silently substitute a
different tool; an explicit executable path remains authoritative.

## Release identity

`VERSION` is the release-train identifier. Before a tag exists, it must be
strictly newer than the latest release and its material remains under
`Unreleased`. A release commit moves that material to a dated heading and is
tagged as exact `v<VERSION>` on the same UTC date. A release candidate must
satisfy all of the following:

- `VERSION`, runtime version lookup, and the dated Changelog heading agree;
- `CHANGELOG.md` starts with one `Unreleased` heading and keeps the shared
  cross-provider chronology in descending order. GitLab's canonical plane
  requires complete history, every non-pending release heading to have a
  provider-native tag, and each heading date to match the UTC date of GitLab
  tag creation. A GitHub projection may retain canonical or legacy headings
  absent from its tag namespace, but every GitHub-native tag still requires
  exactly one heading. Its independently signed native tag date may differ and
  does not rewrite the GitLab-owned chronology. Ordinary GitHub main validation
  checks this native subset and rejects a stale active release train without
  invoking GitLab-only release preparation;
- repository metadata and quality pass, combined, statement-only, and
  branch-only coverage each reach at least 95%, and the complete platform matrix
  passes;
- the tag is a signed annotated tag that directly identifies the release commit;
- claims distinguish source structure, Forge publication, local installation,
  physical host acceptance, and original-task recovery.

A tag is source identity, not publication proof by itself. No candidate may be
installed before both Forge planes have completed their signed tag, required CI,
and formal Release record.

## Independent Forge publication proof

GitLab and GitHub are equal, independent publication planes. Each owns its
signed tag object, hosted CI execution, and Release record, while both publish
the same forward-only ordered tree history through provider-specific commit identities.

Commit history is immutable collaboration evidence, not a provider-specific
projection. Every accepted commit is authored and signed once before landing;
publication may only fast-forward `main`. Automation must not recreate the DAG,
change attribution, or force-update a branch. Existing commits, tags, and
Release objects remain historical evidence. Divergence requires an explicit
migration decision outside ordinary release automation.

`tools/release/verify.py` is the in-repository, read-only verifier.
It fetches each exact tag into isolation, verifies each provider signature under
its own external anchor, observes the policy-required hosted jobs and Release
record, and requires the two tags to bind the same source tree. Its JSON is
audit evidence only and is not an installation input.
Remote authentication remains the caller's explicit transport concern; the
verifier clears ambient Git configuration and never injects a credential helper.
API authentication remains with `glab` and `gh`; tag fetches use the supplied
Git remote and its native external transport context. Prefer SSH and never put
tokens or passwords in a remote URL.

The source-side installer consumes one caller-selected release source and its
external trust anchor without requiring Forge access. Admission checks clean
state, requires `HEAD` to be the exact signed annotated `v<VERSION>` tag, and
reads payload bytes from Git objects,
never from an arbitrary working-tree stage. Before capability minting, it
compares the frozen `HEAD`, tag object, tag commit, tree, and object format,
requires a final clean checkout, then compares the same identity again. Dirty
state and clean ref movement both fail closed. `codex_responses_proxy.release.admission`
returns an opaque one-use capability binding signed source identity, payload
blobs and modes, aggregate serving identity, receipt, and sidecar.

## Installation transaction

Every payload mutation is owned by source-side
`python3 -m codex_responses_proxy.commands.install`. The installer consumes the
release capability into one private transaction that owns commit,
rollback snapshot, installed-release state, and recovery hold. The separate
installed-projection owner defines and verifies the manifest, writes the
canonical receipt, and enforces manifest-bounded purge. The transaction refuses
downgrades and same-version replays and finalizes only after the accepting
listener proves release, aggregate serving-payload digest, release-receipt
digest, and manifest digest.

The private transaction is same-process rollback coordination, not signed
evidence. Directory permissions exclude other local users, but same-UID process
tampering is outside its integrity boundary; the admitted release signature and
installed manifest remain the authenticity owners.

Failure before a proven terminal state restores the exact previous owned
projection. If a committed handoff result is unknown, the transaction is kept as
`recovery_required`; neither success nor rollback may be inferred. Installed
control exposes no arbitrary stage-path upgrade and no controller-only partial
apply. Plain release archives are not installation sources because they cannot
carry the signed annotated tag object.

Recovery remains source-side and signed-release-gated. The installer may restore
only the exact retained rollback snapshot while the live accepting listener's
frozen release, serving digest, and receipt digest match that prior projection;
its reported manifest digest matches the fully verified candidate projection
committed on disk; its handoff state is idle; and the PID is uniquely bound to
the installed entrypoint. It then begins a new admitted release transaction.
An explicitly authorized protocol-v2 bootstrap binds one idle
accepting listener to its exact installed entrypoint before termination and
must prove either the released successor or the restored prior runtime.

Retired raw captures are a separate privacy cleanup: their exact filenames are
removed before a transaction is prepared and their contents never enter the
rollback snapshot. Retired install-owned executable paths are different; the
snapshot first preserves any prior owned bytes, and commit then removes those
paths from the candidate projection so a failed deployment can restore them.

Endpoint changes remain wholly outside this repository and belong to the
consumer control plane, such as AIGW.

## Lifecycle operations

`python3 -m codex_responses_proxy.commands.control status` is read-only.
Installed-control `reload` is same-payload only and requires a user-visible warning plus post-operation
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
historical-manifest integrity, exactly one PID bound to the manifest-derived
legacy entrypoint, and a bounded zero-active quiet window. Candidate commit then
terminates only that bound process and replaces native supervision before
successor proof; failure restores the owned projection. The same historical
verifier governs transaction snapshot and purge. `--force-legacy-bootstrap`
adds separate interruption authorization; it skips only the quiet wait, is
unavailable to `reload`, is rejected without the allow flag, and never applies
to a current protocol-v2 listener. Rollback after old-process exit also restores
the historical supervision entrypoint and requires accepting runtime proof; an
unproven restoration is a rollback failure, never a successful rollback claim.

Uninstall has two distinct authority boundaries. It never reads or changes
consumer endpoint configuration. Native-service deregistration must be confirmed as `absent`, and each
owned watchdog or listener must be identified by a Python executable plus exact
resolved script in `argv[1]`, rechecked before signalling, and boundedly proved
gone before payload mutation. A purge trusts only a valid current manifest or an
exact supported historical inventory; unknown claims fail closed, while unknown
physical content is preserved and produces a nonzero incomplete result.

## Reliability observation and incident boundary

`python3 -m codex_responses_proxy.commands.control status --json` is the
secret-free source of listener-local counters. `tools/reliability/observe.py` evaluates a supplied snapshot and optional
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
