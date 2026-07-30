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
checks do not retain a Ruff cache in the checkout.

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

GitLab and GitHub are equal, independent authority planes. Each owns its commit
history, signed tag object, CI execution, and Release record. GitHub is projected
from the canonical GitLab tree through a fresh isolated clone, but its commits
and tags retain GitHub-native identity.

Provider history is a release invariant, not cosmetic attribution. Every commit
reachable from provider `main` has the provider's sole author and committer
identity and a provider-trusted SSH signature. Historical correction therefore
recreates the full DAG while preserving tree, parent topology, message, and
dates, then replaces `main` only under an exact remote-tip lease. Existing tag
and Release objects are immutable historical evidence and are never silently
rewritten to pretend that their original target commits changed.

`scripts/verify-publication-proof.py` is the in-repository, read-only verifier.
It fetches each exact tag into isolation, verifies each provider signature under
its own external anchor, observes the policy-required hosted jobs and Release
record, and requires the two tags to bind the same source tree. Its JSON is
audit evidence only. Installation repeats live verification in the same process;
no serialized document can be converted back into installation authority.
Remote authentication remains the caller's explicit transport concern; the
verifier clears ambient Git configuration and never injects a credential helper.
API authentication remains with `glab` and `gh`; tag fetches use the supplied
Git remote and its native external transport context. Prefer SSH and never put
tokens or passwords in a remote URL.

The source-side installer requires a clean checkout before live publication
verification. Admission checks clean state again, requires `HEAD` to be the exact
signed annotated `v<VERSION>` tag, and reads payload bytes from Git objects,
never from an arbitrary working-tree stage. Before capability minting, it
compares the frozen `HEAD`, tag object, tag commit, tree, and object format,
requires a final clean checkout, then compares the same identity again. Dirty
state and clean ref movement both fail closed. `codex_dmx_proxy.release.admission`
returns an opaque one-use capability binding source identity, publication proof,
payload blobs and modes, aggregate serving identity, receipt, and sidecar.

## Installation transaction

Every payload mutation is owned by source-side `install.py`. The installer
consumes the release capability into one private transaction that owns commit,
rollback snapshot, installed-release state, and recovery hold. The separate
installed-projection owner defines and verifies the manifest, writes the
canonical receipt, and enforces manifest-bounded purge. The transaction refuses
downgrades and same-version replays and finalizes only after the accepting
listener proves release, aggregate serving-payload digest, release-receipt
digest, and manifest digest.

The private transaction is same-process rollback coordination, not signed
evidence. Directory permissions exclude other local users, but same-UID process
tampering is outside its integrity boundary; publication signatures and the
admitted release remain the authenticity owners.

Failure before a proven terminal state restores the exact previous owned
projection. If a committed handoff result is unknown, the transaction is kept as
`recovery_required`; neither success nor rollback may be inferred. Installed
control exposes no arbitrary stage-path upgrade and no controller-only partial
apply. Release archives are not installation sources because they cannot carry
the signed annotated tag object and its verified publication chain.

Retired raw captures are a separate privacy cleanup: their exact filenames are
removed before a transaction is prepared and their contents never enter the
rollback snapshot. Retired install-owned executable paths are different; the
snapshot first preserves any prior owned bytes, and commit then removes those
paths from the candidate projection so a failed deployment can restore them.

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

Uninstall has three distinct authority boundaries. Route restoration changes
only exact managed state and preserves drift, but is not atomic with later
cleanup. Native-service deregistration must be confirmed as `absent`, and each
owned watchdog or listener must be identified by a Python executable plus exact
resolved script in `argv[1]`, rechecked before signalling, and boundedly proved
gone before payload mutation. A purge trusts only a valid current manifest or an
exact supported historical inventory; unknown claims fail closed, while unknown
physical content is preserved and produces a nonzero incomplete result.

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
