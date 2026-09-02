## Context

See [proposal.md](proposal.md). This Change is the sole active repository-wide
convergence carrier. Its tasks are the progress authority; no parallel roadmap,
quality backlog, compatibility matrix, or cleanup ledger will be added.
Implementation may use multiple signed atomic commits, but all remain in this
one Work Lane and close requirements from this one Change.

The accepted product is a local Responses data plane. It receives one supported
Responses request, validates and projects it to one configured upstream wire
contract, returns one faithful Responses result, and owns only its installed
payload, local listener, native supervisor, transaction state, and bounded
operational output. It does not own client configuration, model choice,
credentials, conversations, repository governance, or Forge identity.

## Goals / Non-Goals

**Goals:**

- Reconstruct the repository from product semantics rather than preserve its
  current file tree.
- Assign every retained source, test, tool, configuration, document, workflow,
  and artifact to one semantic owner and one dependency direction.
- Delete duplicate owners, obsolete carriers, compatibility paths, historical
  residue, and custom mechanisms superseded by mature tools.
- Prove supported behavior through clean-room development, installed wheels,
  native artifacts, real operating systems, installed lifecycle transitions,
  and both optional Forge publication planes.
- Keep the current working installation available until an exact accepted
  successor asset has passed the corresponding transition proof.

**Non-Goals:**

- Add AIGW, Codex session, client-profile, credential-manager, or model-selection
  responsibilities to this repository.
- Copy ETHOS lifecycle, Lease, Commitment, Attestation, or branch-transition
  semantics into product code.
- Retain an old path solely for compatibility, preserve an entity because it
  exists, or add a second framework when the existing authority can carry the
  requirement.
- Treat a container, mock, syntax check, or another operating system as native
  evidence for an unavailable platform.

## Decisions

### One Change, ordered semantic closures

The Change is large by design, but implementation is not a big-bang edit. Each
ordered task group closes one semantic boundary through RED, one owner, deletion
of the incumbent path, focused GREEN, and one affected gate. Heavy gates run
only at milestone boundaries. A task is complete only when its stated evidence
exists; file churn or an unexecuted design does not count as progress.

### Product ontology determines physical topology

The durable product domains are request admission, portable Responses
semantics, Provider wire adaptation, relay transport, runtime configuration,
installed payload generations, lifecycle transactions, native supervision, and
public CLI presentation. Repository-only domains are development bootstrap,
quality, CI projection, release construction, Forge transport, and publication
verification. Tests mirror these owners by behavior. Files do not distinguish
roles by accumulated suffixes such as `publish_github.py`, `publish_gitlab.py`,
or `*_manager.py`; provider differences live behind adapters within the one
owning semantic package.

A package survives only when it owns a distinct invariant and dependency
boundary. Catch-all packages and names such as `common`, `shared`, `utils`,
`helpers`, `misc`, `manager`, or `service` are not terminal names. Existing
`service` usage is decomposed by actual runtime, supervision, handoff, and
entrypoint ownership instead of being preserved as a generic bucket.

### Positive topology is the architecture authority

One declarative topology covers product source, repository tools, tests,
configuration, specifications, documentation, workflows, generated projections,
and root files. It declares owners, allowed edges, public entrypoints, generated
outputs, and retirement conditions. New undeclared entities fail because they
lack a positive owner, not because their names appear on a growing forbidden
list. Exceptions are typed, justified, expiring, and consumer-bound; free-text
baselines and permanent suppressions are not admission.

### Mature tools own generic mechanics

Ruff, Ty, pytest and focused plugins, coverage.py, Bandit or another selected
Python security analyzer, deptry, markdownlint, a Markdown formatter, lychee,
Taplo, actionlint, CUE, gitleaks, pip-audit or OSV-compatible scanning, Syft,
Git, OpenSSH, uv, mise, and Nox are evaluated against their supported scope.
Custom repository code remains only for product semantics, cross-file authority,
release identity, exact native ownership, or CI projection that an upstream tool
cannot express. Adoption requires net reduction in custom code and authorities;
a tool is rejected when configuration and maintenance exceed the mechanism it
would replace.

### One development and supply-chain control plane

`mise` selects locked cross-platform tools and exposes the small developer task
graph. uv owns Python resolution and per-Work-Lane environments. npm owns only
the locked Node tools still required by OpenSpec or documentation. Nox owns the
Python verification matrix. Each Work Lane gets independent mutable `.venv`,
`.nox`, `node_modules`, build, coverage, and test-temporary state; only
content-addressed caches are shared. Bootstrap is an idempotent reconstruction
from locks, never an ambient-system repair.

Direct runtime, development, action, image, and release-tool versions are
verified online at the time of the supply-chain task, advanced to current stable
releases, locked, and tested. No version is considered current merely because a
prior audit said so. Pixi, Nix, Bazel, Just, Task, shell wrappers, and another
update bot are not added unless a proved requirement cannot be carried by this
control plane.

### One native process environment contract

`tools/release/native/environment.py` owns derivation of native child-process
environments for release construction and black-box acceptance. It preserves
the supported host execution substrate, removes inherited Proxy and Python
injection state, redirects all product-owned roots to test-owned locations, and
accepts an explicit empty product `PATH`. Fixtures, packaged CLI contracts, and
Nox consume it directly. Partial environments, Windows `SystemRoot` exceptions,
and platform environment allow-lists are deleted.

### One lifecycle state machine, three native adapters

The lifecycle core owns prepare, verify, commit, observe, rollback, recovery,
and retirement. macOS launchd, Linux systemd, and Windows Service Control
Manager adapters translate only native service operations. Creation and teardown
consume the same exact service target, paths, executable identity, process
generation, and transaction. Successful, failed, timed-out, and interrupted
tests prove no net native-resource growth and preserve unrelated canonical
installations.

Environment variables remain the portable non-interactive Provider-secret
input. Secret storage and client projection are outside this product. The Proxy
never opens a keyring, changes Codex or Claude configuration, or requires AIGW.

### One CI model, two optional Forge projections

CUE owns stages, jobs, dependencies, triggers, matrices, platform claims,
artifacts, cache identities, and release admission. GitHub Actions and GitLab CI
are generated projections and are checked for drift. Review SHA, proposal update,
maintainer fast-forward, `dev` promotion, `main` promotion, and tag pipelines
have explicit coverage. Equivalent exact-SHA evidence may be reused through a
revision-bound attestation; repeated jobs that prove no additional fact are
removed.

GitHub and GitLab are optional peer publication planes. Local source remains
fully buildable and installable without either. The same signed local commit and
tag object are pushed unchanged; each Forge supplies independent authentication,
CI, Release records, and asset transport. A missing GitLab Windows runner does
not erase Windows evidence already proved by the GitHub native runner, but the
GitLab projection must state that it does not provide that platform proof.

### Evidence and documentation are reader paths, not residue stores

Current acceptance is reconstructed from exact Git state, test and quality
results, OpenSpec, ETHOS-selected Attestations, signed release assets, and
observed runtime state. A tracked `evidence/`, Claim, Chronicle, parity tree, or
records directory survives only with a current unique consumer and retention
contract. Historical explanation belongs in immutable OpenSpec archives,
Decision Records, Changelog, release records, or Git history.

Documentation follows reader intent: product overview, concepts, setup and
operations, architecture, contribution, governance, and decisions. Every
content filename names its subject; every directory index has a navigation job.
Decision Records use `dr-<sequence>-<subject>.md`. Examples are executable and
production-shaped, never toy placeholders. Prose, tables, commands, links, and
configuration are formatted and verified.

### SemVer and destructive retirement

`VERSION` is the sole release identity. Public incompatibility determines the
next SemVer value; internal restructuring alone does not force a major release.
Changelog retains every formal release. Published releases are immutable.
Merged proposal branches, failed unpublished intermediates, retired Work Lanes,
old hooks, orphaned runtimes, temporary services, caches, and generated residue
are removed once exact ownership and lack of consumers are proved. Deletion is a
first-class task, not deferred housekeeping.

## Risks / Trade-offs

- **The broad Change becomes an excuse for an unreviewable patch** → keep one
  Change but use ordered atomic commits, focused proofs, and task-level
  acceptance; never combine unrelated mutations in one commit.
- **Topology work destabilizes the working service** → preserve the accepted
  installed release until a signed candidate passes native lifecycle proof;
  source restructuring does not mutate the active service.
- **Strict quality expansion creates arbitrary vetoes** → every rule records
  risk, scope, measurement, false-positive cost, remediation, and review
  condition; unsupported or redundant rules are rejected rather than enabled
  performatively.
- **Latest dependencies introduce regressions** → update one authority at a
  time, regenerate locks, run clean-room and affected-platform proof, and keep
  published assets immutable.
- **Dual-Forge automation produces different Git objects** → create and sign
  commits and tags locally once; Forges only receive exact objects and publish
  independent projections.
- **Destructive cleanup removes user or foreign state** → delete only exact
  product-owned, lease-owned, manifest-owned, branch-owned, or unreferenced
  entities after a read-only inventory and consumer proof.

## Migration Plan

1. Establish the full Change, capability deltas, task map, and exact current
   baseline; keep the installed product untouched.
2. Close the Windows native-environment P0 and prove the exact candidate on
   macOS, Linux, and Windows before any release mutation.
3. Freeze product ontology and dependency directions, then migrate one domain
   at a time while deleting each superseded owner in the same atomic commit.
4. Converge the CLI, Responses path, native lifecycle, development environment,
   quality system, CI model, supply chain, documentation, and release system in
   dependency order.
5. Run the complete local and native verification ladder once on the frozen
   candidate; repair failures at their smallest owner rather than rerunning the
   whole graph for discovery.
6. Land through current ETHOS authority, project the same signed objects to both
   optional Forges, publish immutable assets, and prove installed upgrade,
   no-op, rollback, recovery, re-upgrade, uninstall, and reinstall.
7. Remove proposal branches, the Work Lane, superseded local and remote
   artifacts, native test resources, caches, and consumerless records; then
   archive this Change and verify the repository family is terminal.
