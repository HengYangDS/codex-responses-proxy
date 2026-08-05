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

## Lane retirement

A work lane is retirable when its findings are demonstrably present in the
product and its working tree holds nothing unrecorded. Presence is shown by
naming the file, spec, or setting that carries the finding today, not by
asserting that the lane was merged; a lane whose branch root is disjoint from
the current line can never have been merged and must be checked this way.

Uncommitted work is committed before its worktree is removed, on the lane's own
branch and with a message stating what the work is and why it cannot move
forward. Deleting a worktree that holds unrecorded work destroys it; committing
first costs nothing and is reversible. Worktrees are removed, branches are kept:
removing a worktree can be undone from the branch, and deleting the branch
cannot be undone.

A lane with recent write activity is active regardless of how old its last
commit is, and is never retired, committed into, or removed by anyone but its
owner. Working-tree state, not branch position, decides this: a lane can sit on
an already-merged commit and still hold substantial in-flight work.

Branches outlive their worktrees under an explicit namespace. `work/*` is a live
lane; `archive/1.x/*` and `archive/2.x/*` are retired records kept only for
recovery. A retired lane is renamed rather than deleted, unless its tip is
already held by another ref and it carries no unique commit.

Work that lives in a temporary directory and is reachable from no ref is one
directory sweep away from destruction. It is recovered onto a branch when found,
using a snapshot primitive that does not disturb the worktree or the shared
stash stack.

Recorded retirement, 2026-08-04. Four lanes sit on the disjoint 1.x root
`fc8d76c5`, which the 2.x root `941e930d` can never merge, so each was verified
by naming its carrier and then renamed under `archive/1.x/`:
`empty-tool-output-replay` (`86a4a08`) is carried by
`codex_responses_proxy/replay/request.py` and
`tests/providers/test_portable_requests.py`; `transaction-semantic-split`
(`bad87ed`) by `codex_responses_proxy/listener/handoff/transaction.py` and
`codex_responses_proxy/payload/transaction.py`; `function-eloc-ratchet`
(`7e85adf`) by `pyproject.toml` `function-max-eloc` enforced in
`tools/quality/repository.py`; `provider-portable-runtime-acceptance` (`f01a50d`)
covered v1.0.44 and v1.0.45, whose headings the 2.x chronology retains without
the code line. The first two had held complete but never-committed changes and
were committed before their worktrees were removed.

`work/20260803-provider-concurrency-portability` was deleted rather than
archived: its tip `74ca0eb` is simultaneously `main`, `v2.0.7`, and both GitLab
remote heads, and it carried no unique commit.

An orphaned evaluation worktree under `/private/tmp` held HEAD `b8c318b`
reachable from no branch and no tag, with 179 files of unrecorded work above it.
Its three commits proved tree-identical to `6cc5457`, `e7c4794`, and `584e1a8`,
so only the working state was at risk. It is preserved as `94a9496` on
`archive/2.x/terminal-product-restructure` and absorbed nowhere: its module
renames duplicate an active lane, its `.githooks/` contradicts the
`core.hooksPath=/dev/null` this product sets in
`codex_responses_proxy/release/admission.py`, and its four OpenSpec changes are
all incomplete, `terminal-product-closeout` most of all at 30 open tasks
against 2 done.

`work/20260803-terminal-product-reconstruction` was not retired: it holds an
uncommitted `src/` layout migration and belongs to its owner.

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
  provider-native remote tag, and each heading date to match the UTC date of GitLab
  tag creation. A GitHub projection may retain canonical or legacy headings
  absent from its tag namespace, but every GitHub-native tag still requires
  exactly one heading. Its independently signed native tag date may differ and
  does not rewrite the GitLab-owned chronology. Ordinary GitHub main validation
  checks this native subset and rejects a stale active release train without
  invoking GitLab-only release preparation;
  hosted verification selects `origin` through
  `CODEX_RESPONSES_PROXY_RELEASE_TAG_REMOTE`; an operator may select another
  repository-local remote explicitly. Unpublished local candidate tags never
  mint Changelog release history;
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
signed tag object, hosted CI execution, Release record, verified commit email,
and signing trust. GitLab `main` carries the accepted canonical commits. GitHub
`main` is an append-only identity projection with equivalent ordered trees,
messages, dates, and parent topology after its admitted base.

Published history is immutable within each Forge: ordinary publication only
fast-forwards `main` and never changes an existing commit, tag, Release, or
evidence record. When a disconnected GitLab tip has exactly one
identity-neutral match in accepted history, an explicit migration may replay
only unpublished accepted descendants onto that exact tip and re-sign them in
the GitLab identity domain. It must not merge duplicate identity-equivalent
histories or force-update either Forge. After convergence, ordinary GitLab and
GitHub projection resumes from the unique admitted base.

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

The release installer consumes one caller-selected release source and its
external trust anchor without requiring Forge access. Admission checks clean
state, requires `HEAD` to be the exact signed annotated `v<VERSION>` tag, and
reads payload bytes from Git objects,
never from an arbitrary working-tree stage. Before capability minting, it
compares the frozen `HEAD`, tag object, tag commit, tree, and object format,
requires a final clean checkout, then compares the same identity again. Dirty
state and clean ref movement both fail closed. `tools.release.admission`
returns an opaque one-use capability binding signed source identity, payload
blobs and modes, aggregate serving identity, receipt, and sidecar.

## Installation transaction

Every payload mutation is owned by
`codex-responses-proxy install`. The installer consumes the
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

Recovery remains release-gated. The installer may restore
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

`codex-responses-proxy status` is read-only.
Installed-control `reload` is same-payload only and requires a user-visible warning plus post-operation
identity proof. It prepares a non-accepting child, stops the old accept loop
before `COMMIT`, and requires `SERVING` proof by PID, transaction, release,
aggregate serving-payload digest, release-receipt digest, and manifest digest
before `FINALIZE`. Accepted handlers drain to zero or the bounded lease.
Pre-finalize failure confirms child exit before old admission resumes; an
unconfirmed abort fails closed.

Replacing payload bytes is a release install operation. For a current
protocol-v2 listener, deployment commits the admitted release
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
owned watchdog or listener must be identified by the exact installed executable
plus one declared private service role, rechecked before signalling, and boundedly proved
gone before payload mutation. A purge trusts only a valid current manifest or an
exact supported historical inventory; unknown claims fail closed, while unknown
physical content is preserved and produces a nonzero incomplete result.

## Reliability observation and incident boundary

`codex-responses-proxy status --json` is the
secret-free source of listener-local counters. `tools/reliability/observe.py` evaluates a supplied snapshot and optional
explicit baseline file; it does not contact the listener, mutate configuration,
retain request or response material, or perform lifecycle control.

Counters are comparable only when release, startup-frozen aggregate
serving-payload digest, and monotonic uptime identify the same running payload.
A first snapshot, restart, or payload change starts a new observation window;
lifetime counters and `last_failure` are not reclassified as new incidents.
Payload-integrity failure, missing or multiple verified listeners, local stream
failures, and pre-content exhaustion are immediate local incidents. Drain
rejections remain a separate local class: approved maintenance
may classify them as `observe`, never as upstream failure.

Upstream `empty_response`, retryable 5xx, `response_failed`, and the exact input-
variant validation class are evaluated independently. One or two new events in
a comparable window require observation; three or more require an incident.
These gates prove only the stated runtime evidence. Historical Codex task
recovery requires a separate acceptance result from that exact task after a
released runtime is serving.
