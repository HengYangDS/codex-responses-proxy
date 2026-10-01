# Design

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

## Product Positioning and Name

The terminal data-plane contract is OpenAI Responses, not every API commonly
called "OpenAI-compatible". Provider admission is declarative and independent of
provider brand; a Chat Completions-only endpoint does not qualify. Codex is the
first qualified client, but generic request admission must not require Codex
identity. Codex-specific historical replay belongs to a narrow compatibility
policy rather than the common Responses grammar. Other clients require their own
real request, replay, stream, error, and installed-client acceptance before the
product claims support.

The target public name is **Responses Proxy**, not `openai-proxy`. Change the
package, command, service, and release identity together at a major release only
after a non-Codex Responses client passes that bar; remove the old identity in
the same transition rather than maintain aliases. Until then, retain the
truthful shipped name **Codex Responses Proxy**. Naming does not expand the
protocol surface or move Account, credential, model, or client-projection
authority out of AIGW or another control plane.

## Goals / Non-Goals

**Goals:**

- Reconstruct the repository from product semantics rather than preserve its
  current file tree.
- Assign every retained source, test, tool, configuration, document, workflow,
  and artifact to one semantic owner and one dependency direction.
- Delete duplicate owners, obsolete carriers, compatibility paths, historical
  residue, and custom mechanisms superseded by mature tools.
- Prove supported behavior through clean-room development, installed wheels,
  native artifacts, real operating systems, installed lifecycle transitions, and
  both optional Forge publication planes.
- Keep the current working installation available until an exact accepted
  successor asset has passed the corresponding transition proof.

**Non-Goals:**

- Add AIGW, Codex session, client-profile, credential-manager, or
  model-selection responsibilities to this repository.
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

The durable product domains are request admission, portable Responses semantics,
Provider wire adaptation, relay transport, runtime configuration, installed
payload generations, lifecycle transactions, native supervision, and public CLI
presentation. Repository-only domains are development bootstrap, quality, CI
projection, release construction, Forge transport, and publication verification.
Tests mirror these owners by behavior. Provider differences live within the
owning semantic package, rather than in suffix-named sibling files.

The protocol package separates request-local replay from failure recovery and
live response validation. `replay` owns item relationships, content projection,
and whole-request projection. `recovery` consumes those rules to handle input
validation and execution failures; it does not own another replay grammar.
`response` validates live wire data without rewriting it. Tests mirror replay
projection, content, history, admission, and recovery instead of suffix
families; shared request encoding belongs to their fixture, not another test
module.

The release publication package owns one command tree and one subpackage per
Forge. Within each Forge, publication writes and hosted observations are
distinct operations. Cross-Forge verification consumes observations; artifact
assembly and signing remain release-construction concerns. Git reference
projection, repository settings, and runner admission remain Forge concerns
rather than a second release publication mechanism.

Publication identity includes what users can download, not merely a matching
asset-name inventory. The GitLab adapter compares the complete expected link
records (name, URL, type), allowing only response ordering and server-assigned
metadata to vary. Every success path ends by reading and validating the
persisted Release after verifying package bytes, including first creation,
existing Release reuse, and concurrent creation. Signed package verification and
Release-link verification protect different boundaries; neither replaces the
other. An isolated HTTP store proves these adapter contracts without claiming
real Forge publication or changing an installed product.

Release construction has one semantic owner under `tools/release/artifact`.
`bundle` normalizes frozen inputs and packages one native target; `format` owns
archive, manifest, and checksum grammar; `assembly` admits one complete release
set; `signing` owns the external OpenSSH trust boundary. One command tree
exposes `normalize`, `pack`, `assemble`, and `verify`. Publication adapters
consume these owners without creating another asset grammar or coordinating
build internals. The `verify` operation authenticates the signature against
explicit external trust before reporting success; signature-file presence is not
authentication. Both Forge publishers consume that same complete verification
boundary. Tests follow bundle, format, assembly, and signing semantics. The
former flat asset entrypoints and declaration-only publication initializer are
removed.

Repository-specific quality checks share the `tools.quality.repository` package:
topology, names, and decision records feed its existing audit command. Tests
import each actual owner directly rather than reload files under synthetic
module names. The unused worktree fingerprint command and implementation are
removed; no replacement state authority or compatibility import remains.

A package survives only when it owns a distinct invariant and dependency
boundary. Catch-all packages and names such as `common`, `shared`, `utils`,
`helpers`, `misc`, `manager`, or `service` are not terminal names. Existing
`service` usage is decomposed by actual runtime, supervision, handoff, and
entrypoint ownership instead of being preserved as a generic bucket.

Lifecycle control tests follow status, recovery, reload, rollback and uninstall
semantics; loopback transport belongs to runtime tests. Their shared installed
listener evidence stays in the existing lifecycle fixture, not an umbrella test
class or another fixture framework. Pytest owns temporary test directories and
retires them through its native retention policy; tests do not allocate unowned
`mkdtemp` roots. Explicit per-operation output roots retain their own cleanup
owner, and required failure evidence is copied to source-bound verification
output before scratch retirement.

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

### Quality acceptance protects product invariants, not a green dashboard

Public outcome admission validates the operation, not only its JSON shape. A
completed reload requires distinct positive predecessor and successor process
IDs. Cleanup reports a nonnegative integer process count; zero remains valid
when there was no live listener to stop. The existing outcome owner rejects
inconsistent evidence before either human or machine rendering, without adding a
second result schema or changing valid lifecycle output.

Fresh-install failure retains its initial boundary when native cleanup or
payload rollback also fails. Public causes remain readable; arbitrary exception
messages become bounded operation labels, not paths, types or secret-bearing
native output. Unavailable service admission still triggers only payload
rollback, never native cleanup. Unconfirmed runtime cleanup preserves the
existing recovery journal. Generation removal reports the operating system's
numeric error without its absolute path; a compensation error cannot hide the
startup failure that required it. Failed recovery-record persistence is reported
as unconfirmed, never as a retained transaction whose write did not succeed. The
outer install entrypoint retains the original public code and next command when
prepared cleanup fails. Both layers use the existing shared error owner; there
is no second cause formatter or exception vocabulary.

The quality system has four distinct obligations: a useful policy, a correct
measurement, a complete execution path, and a working product. Passing one does
not establish the others. The responsibility map assigns concerns; native tool
configuration defines their executable rules; Nox invokes them; CUE projects the
same obligations into each Forge. No second checker, registry, or workflow may
independently define the same rule.

English quality uses one native Vale CLI for spelling, repeated words, canonical
terms, and concise prose. Its native configuration and vocabulary belong under
the existing quality configuration owner. The governance graph selects all
tracked current Markdown once, including OpenSpec, without archived or private
inputs. Real command probes cover paragraphs, quotes, and table cells and leave
code, identifiers, and link destinations untouched. Rules cannot silently remove
an actor, obligation, qualification, or evidence limit to make prose pass. Style
checks do not prove semantic completeness or factual correctness.

Vale supports document-level disabling comments; `--no-global` does not prevent
them. Native ignore-pattern trials changed paragraph boundaries and missed a
repeated word across an inline comment, so they are rejected. The existing
Markdown linter instead uses one native micromark rule to reject actual Vale
control comments in all current documents. It preserves literal code and normal
comments and runs native Node tests through the same governance entry. The
Markdown linter configuration is one native module. Native HTML callbacks
identify actual comments, and the native entity decoder matches Vale's comment
interpretation without treating attribute or escaped example text as a control.
Its code and the vocabulary retain the existing tracked text-byte policy.

The initial textlint/write-good candidate was rejected after real quote and
table counterexamples exposed its native plain-paragraph-only scope. Copying
DDWG's custom adapter would retain another parser and linguistic implementation.
Vale's built-in spelling, repetition and vocabulary checks cover those same
inputs; one small native substitution rule removes specific needless phrases
without a new NLP engine. The rejected npm dependencies and draft configurations
are retired, not kept as fallback or a second command plane. General policy will
be reconciled at the accepted ETHOS quality owner; repository-native prose
checks do not grant lifecycle proof.

Prettier owns current Markdown, YAML, JSON and JSONC formatting through the
existing governance command. Git's exact tracked inventory includes hidden
configuration and package-manager inputs; an untracked private file or immutable
OpenSpec archive is not a current formatting input. The same native check
rejects malformed or unformatted JSON without rewriting source. Editor defaults
and text-byte validation cover those carriers too. Adding a format does not add
a second formatter, schema, executor or dependency.

Nox's native fail-fast option stops the ordered full graph at the first failed
prerequisite. Governance failure cannot start quality or compatibility work;
quality failure cannot start later interpreter sessions. A valid full run still
executes every declared session. Failure diagnostics remain evidence, not a
reason to continue dependent work or report partial acceptance.

Cold development verification starts with a complete immutable local checkout,
including release tags required by Changelog provenance. Native Mise config-dir
and ceiling selection excludes ambient host and parent configuration while
retaining the exact project config. A missing project config is failed input,
not isolation success. Package caches and mutable environments remain private.

Mise's tool-aware late `UV_PYTHON` directive is the single locked interpreter
binding for local tasks, direct proof commands, and native CI. Native locked
synchronization reconstructs a missing or stale generated `.venv` before
execution and rejects an out-of-date dependency lock without changing source.
No-sync execution, an executable-name request, and a private interpreter checker
are not substitute acceptance. The governance graph exercises the actual
consumer commands under nested paths containing spaces. Image-owned Linux
commands keep their explicit runtime selection; neither policy changes a
supported Python version or suppresses a mismatched-environment warning. Native
macOS and Windows jobs execute the same conformance before constructing their
release candidate, rather than inferring portability from local success.

Native signing fixtures retain deeply nested HOME as a real input. OpenSSH's
default HOME-relative socket can exceed the Unix path limit; the fixture uses
standard-library native temporary storage for an explicit short socket and owns
one foreground agent. It waits for that exact process to exit before removing
its socket directory, including failed key setup and assertion exits. Operator
credentials and authentication agents remain outside the fixture.

Quality inventory binds Git's directory and working tree to the requested
checkout, rather than treating the command's current directory as repository
identity. Native Git resolves both regular `.git` directories and linked-lane
`.git` files. A nested non-checkout must fail instead of inheriting its parent's
index and producing a plausible but unauthorized scope. Structure, names, text,
responsibility mapping, and native formatter inputs use this same boundary; each
retains its own explicitly declared tracked or pending-file semantics.

The review at source `268ce99f` established these gaps:

- Structural inventory still reports size observations without ELOC vetoes;
  function size, arguments and statement admission remain open. McCabe
  complexity now has one blocking Ruff `C901` policy across product, tools,
  tests and Nox. The stream reader drops duplicated prelude state and two
  closure layers; declaration identity validation has one owner instead of three
  copies. Their complexity decreases from 24 to 20 and from 22 to 16
  respectively. The current bound of 20 is a reviewed maintainability guard, not
  a claim that every smaller value is better. A bound of 15 identifies nine
  additional operations, including payload validation and transaction-state
  admission; review their semantic risk before fragmenting their state or adding
  facades. The numeric authority remains Ruff configuration, not this
  explanation.
- Function ELOC used a physical line span, while file ELOC removed entire lines
  carrying inline comments. The two measures were neither accurate nor equal.
  Commit `6110515b` repairs that measurement with focused regression evidence;
  this does not complete structural enforcement or the quality system.
- Top-level package admission and a complete file-role inventory did not prove
  cohesion within a package. Lifecycle control and CLI contracts now follow
  their operation boundaries rather than stateless umbrella classes. CLI parsing
  and presentation remain distinct from lifecycle observation, mutation and
  locking; one CLI fixture owns output capture. Relocation preserves test bodies
  and parameterization, rather than manufacturing additional tests or
  introducing a fixture framework. Lifecycle transaction tests, relay fixtures
  and native compatibility journeys remain concrete review targets.
- The former Python coverage configuration omitted repository tools and Nox
  orchestration. Real coverage.py conformance now includes those sources and
  unexecuted namespace modules. The admission command consumes that same native
  configuration and evaluates each source independently; a product aggregate
  cannot establish tool or orchestration coverage. This exposes existing test
  gaps rather than completing them.

The terminal acceptance scopes are explicit:

| Concern                    | Protected invariant                                                              | Executable owner and acceptance                                                                                               |
| -------------------------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Semantics and topology     | One responsibility, state owner, and dependency direction                        | Product ontology plus architecture checks; review real caller edges and mutation ownership, not file counts                   |
| Source correctness         | Typed boundaries, explicit errors, safe concurrency and resource lifetime        | Ruff, Ty, focused behavior tests, then native platform contracts                                                              |
| Structural maintainability | A change remains locally understandable without caller-coordinated recovery      | Native complexity, branches, statements, arguments, and nesting checks; trustworthy ELOC locates module and function hotspots |
| Test quality               | Assertions exercise a product invariant at the correct evidence scope            | Domain tests, failure-path contracts, and native artifact journeys; fixtures own exact cleanup                                |
| Coverage                   | Missing behavior cannot disappear in aggregation or omitted roots                | Coverage configuration declares product and tooling scopes separately; report each supported measurement honestly             |
| Dependencies and security  | No unowned dependency, exposed secret, unsafe update, or unsupported trust claim | Locked dependency, dead-code, secret, vulnerability, license, SBOM, and signature checks at their native owners               |
| Non-code carriers          | Configuration and documentation are current, valid, navigable, and readable      | Native format/lint/schema/link tools plus narrow cross-carrier product contracts                                              |
| Environment and delivery   | The released executable works outside this checkout and shell                    | Locked lane bootstrap, installed-wheel tests, native build and lifecycle acceptance, exact-source CI and assets               |
| Control effectiveness      | A declared failure reaches a nonzero decision everywhere it is required          | Isolated conformance cases run the real tool and configured command; inspect local hooks and CUE event routes                 |

Structural limits are engineering decisions, not universal constants. First
measure with named semantics; then assess the protected risk, current
percentiles, worst legitimate cohesive examples, and native tool guidance.
Reject both a bound chosen just above the current maximum and a number that
forces forwarding helpers or state fragmentation. Product and tooling branches
are executable risk; a long declarative test table is not equivalent, but test
setup, control flow, assertions, and teardown still need bounded ownership. Any
distinct scope needs a semantic reason, never a filename exception for a current
offender. Existing gaps remain open until the chosen final policy passes; an
informational probe is never called a blocking gate.

Ruff remains the first owner for its native complexity rules, documented in the
[rule catalog](https://docs.astral.sh/ruff/rules/). ELOC and logical statements
must be named separately. Module size is reviewed with cohesion and dependency
edges; moving half a function into an alias package does not satisfy either. Do
not add another analyzer until its required metric or behavior is absent from
the admitted tools and its maintenance cost is lower than the displaced custom
implementation.

Complexity conformance runs the locked Ruff module with the actual repository
configuration against each Python role. Boundary and over-bound inputs differ by
one branch; a disabled rule, test exclusion, ignored diagnostic or successful
exit on excessive complexity fails the contract. The existing Nox static-check
owner propagates that result through quick, quality and both CUE projections.
SSE tests separate wire framing from pre-content recovery, retain their original
bodies and parameterization, and cover byte-order preservation for fragmented
input. Downstream commitment is one irreversible state; it does not need a
second prelude-flushed flag or an extra terminal flush.

Topology changes follow complete semantic operations. Review payload admission,
generation transition, rollback/recovery, cleanup, portable replay, and
streaming as distinct invariants. Keep each state transition's validation,
effect, and compensation together. Tests follow those behaviors and separate
unit, integration, native, and release evidence without copying product
implementation structure. Platform filenames may remain when they express real
platform dispatch; generic suffix clusters and fixture buckets must instead be
absorbed, narrowed, or split around real consumers. The acceptance proof is
preserved behavior, fewer parallel owners, and understandable dependencies, not
directory depth.

Quality repair proceeds in this order within the existing task groups:

1. Correct measurement and scope errors, record current effective tool settings,
   and reopen unsupported completion claims. Keep the installed service intact.
2. Consolidate native rule ownership and test the complete invocation/exit path.
   Document selected bounds before changing them; keep unproved scopes open.
3. Resolve product hotspots by invariant, then organize their behavioral tests
   and fixtures in the same closure. Delete displaced code and imports before
   moving to the next owner. Review tooling and non-code carriers by the same
   rule.
4. Enable the agreed blocking policies with no blanket exclusions or permanent
   violation baseline. Run focused checks after each closure; batch independent
   formatter fixes before running expensive proof.
5. Exercise all CI event classes, cold bootstrap, native artifacts and
   lifecycle, security and performance, then freeze one exact candidate for full
   acceptance. Exact applicable proof and current source authority permit a
   releasable increment. Delivery and actual-use obligations consume that
   release; whole-Change archive and lane retirement follow their observed
   completion. Preserve immutable release identity when later task evidence
   updates the active Change.

Generic ETHOS scope, lifecycle, hook dispatch, and capability-reporting defects
belong to ETHOS. Product policy, native tool configuration, tests, and CI remain
this repository's responsibility and continue without waiting for ETHOS changes.

The coverage repair is deliberately limited to that owning boundary: no new
scanner, waiver baseline, product mutation, or quality configuration is added.
Coverage.py owns file discovery and executable counts; the existing admission
command owns the independent source-root decision and its nonzero exit. Product,
tooling, and orchestration each retain the current floor. Their measured gaps
must be resolved through meaningful tests, deletion, or simpler
responsibilities, not by combining denominators or silently reusing a
product-only green proof.

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

Nox's native session installation API owns the target environment and selected
installer. Repository code exports the locked dependency set and requests its
installation; it does not reinterpret `session.python`, which is a version
selector rather than an environment path. The installed-product probe requires
the imported package to resolve beneath that interpreter's installed-package
directory and its manifest beneath the same product package. Merely resolving
outside a temporary working directory does not prove source independence: an
editable `.pth` projection can still point back into the checkout.

Orchestration contracts execute the declared sessions through Nox and observe
their command boundary, environment ownership, ordering, and failure exits.
Artifact admission additionally runs the actual isolated interpreter against
installed and source-linked fixtures. These contracts replace source-string
assertions; they prove orchestration, not native product operation. Artifact
admission and session execution have separate test owners under
`tests/quality/orchestration`, with domain-local fixtures in pytest's native
`conftest.py` carrier.

### One native process environment contract

`src/codex_responses_proxy/runtime/process_environment.py` owns derivation of
native child-process environments for product runtime and black-box acceptance.
It preserves the supported host execution substrate, removes inherited Proxy and
Python injection state, redirects all product-owned roots to test-owned
locations, and accepts an explicit empty product `PATH`. It binds declared user,
payload, and state roots before the child changes working directory. Product
processes, fixtures, and packaged CLI contracts consume it directly. Nox
delegates native acceptance to those contracts instead of implementing a second
command runner. Partial environments, Windows `SystemRoot` exceptions, and
platform environment allow-lists are deleted.

### One lifecycle state machine, three native adapters

The lifecycle core owns prepare, verify, commit, observe, rollback, recovery,
and retirement. macOS launchd, Linux systemd user services, and Windows Task
Scheduler adapters translate only native service operations. The Windows
projection belongs to the current user, not a machine-wide Service Control
Manager service or administrator-owned installation. Creation and teardown
consume the same exact service target, paths, executable identity, process
generation, and transaction. Successful, failed, timed-out, and interrupted
tests prove no net native-resource growth and preserve unrelated canonical
installations.

macOS supervision belongs to the current UID's `user/<uid>` domain, which can
exist without a graphical login. The launch-agent carrier restricts loading to
the `Background` session. The installer neither creates a login domain nor
enables a disabled service. Before mutation, a successful native user-domain
observation determines whether an associated GUI login exists; only then is the
exact legacy GUI service observed. These domains share lookup names but not
service registrations. Concurrent registrations, unavailable observations, or an
unproved watchdog identity reject mutation rather than select a fallback.
Replacement proves the prior process and registration absent before rewriting
the carrier, then proves a distinct successor in the canonical user domain.
Status and teardown observe the same targets, including a registered service
whose carrier has disappeared.

The launch-agent carrier uses the existing owned-file boundary, not direct path
reads or writes. Its home-relative ancestors and leaf must be real directories
and a regular file; its label, native watchdog arguments, user home and
executable inside this installation must agree. An absent carrier is not an
invalid carrier. Installation rejects unowned content before any service
mutation, writes the accepted successor atomically, and teardown rechecks the
exact prior bytes before removing the file. A symbolic link or changed carrier
never grants permission to overwrite or delete its target.

The published 4.0.4 predecessor's own installer requires a GUI domain. Its
authentic installation, health, upgrade and rollback obligation remains a
separate supported-context qualification; headless candidate success cannot
replace it. Native host conservation covers both domain registrations, their
disabled-state overrides and product plist bytes. No protected console user,
synthetic Aqua session, source-built predecessor or skipped predecessor test may
manufacture that evidence.

The transaction journal is one sibling file outside the disposable transaction
directory. After projection and required supervisor binding finish, the
transaction persists its terminal outcome before removing any candidate,
obsolete generation, or rollback snapshot. Recovery of that outcome performs
only disposal and deletes the journal last; it never replays terminal effects or
requires an identity already discarded during cleanup. Interrupted cleanup
continues to block a new transaction. Unrecognized journals and unowned roots
remain protected, not inferred into a cleanup permission.

Controller rollback, interrupted materialization, and serving-generation
recovery share one prior-projection restoration operation. It admits only the
transaction's exact before or after selection; serving-generation recovery also
verifies the prior runtime identity before mutation. Selector restoration and
command restoration are independent durable effects: a restored selector never
proves that the command was restored. Retry completes the missing command before
binding supervision, while an already restored command remains untouched.
Retaining the rollback target changes disposal ownership, not the restoration
algorithm; selection drift remains unowned state in every entrypoint.

Purge uses that same journal after proving native-service absence and owned
process exit. Its terminal record contains the verified, root-relative file
digests. Selection is detached first; disposal checks remaining bytes against
the recorded digests and removes only declared empty parent directories. Neither
a missing payload nor missing metadata invalidates completed removal. Unknown
content or a changed replacement keeps the journal open for deliberate
resolution. Public recovery and repeated purge consume this one disposal owner;
there is no separate uninstall log, retry engine, or inferred recursive
deletion.

A capability-qualified handoff transfers the listener without changing request
admission: the predecessor stops accepting only when the successor is ready to
serve, while already accepted handlers finish on the predecessor. Upgrade and
rollback share this transition. The lifecycle uses draining only for the bounded
legacy native-generation replacement path; handoff state is never presented as
admission state.

Environment variables remain the portable non-interactive Provider-secret input.
Secret storage and client projection are outside this product. The Proxy never
opens a keyring, changes Codex or Claude configuration, or requires AIGW.

### One CI model, two optional Forge projections

CUE owns stages, jobs, dependencies, triggers, matrices, platform claims,
artifacts, cache identities, and release admission. GitHub Actions and GitLab CI
are generated projections and are checked for drift. Review SHA, proposal
update, maintainer fast-forward, `dev` promotion, `main` promotion, and tag
pipelines have explicit coverage. Equivalent exact-SHA evidence may be reused
through a revision-bound attestation; repeated jobs that prove no additional
fact are removed.

GitHub branch admission is a generated branch-only workflow that invokes the
shared Verify graph once. Its stable `Admission` job fails unless the reusable
run succeeds; the graph itself rejects failed or skipped jobs required by the
exact branch event. Tag, release, and dispatch runs cannot emit that required
branch check. Enable branch protection only after a hosted review proves the
check identity, failure behavior, and signed fast-forward path on the exact
candidate. The branch caller passes the published-predecessor trust anchor
explicitly into Verify; it never forwards the release signing key. GitLab keeps
its native successful-pipeline admission rather than a copy of GitHub's check
mechanism.

GitHub and GitLab are optional peer publication planes. Local source remains
fully buildable and installable without either. The same signed local commit and
tag object are pushed unchanged; each Forge supplies independent authentication,
CI, Release records, and asset transport. Once both peers are selected, each
must run the same required macOS, Linux, and Windows functional proof semantics
for the exact revision: triggers, gates, thresholds, produced evidence, and
artifact contracts. A missing runner holds that peer's proof; another peer's
success cannot fill the gap. Provider-native setup may differ without changing
the product obligation. Python-version compatibility and operating-system
function are orthogonal obligations: each peer runs every supported Python
version in a distinct node and proves function on each declared operating system
at the release interpreter. Their Cartesian product is not required. Native
GitLab Shell jobs for merge requests and accepted `dev` use separate
project-bound Runner identities, accounts, working roots, and caches. The source
graph selects review or protected capabilities with mutually exclusive rules and
carries no shared native CI cache; a selector alone does not prove the fleet
isolation. Windows ARM64 qualification must run the locked Windows x64 Python
and uv tools under emulation or replace them with an officially supported lock
path before the job becomes required.

Architecture remains part of the evidence. A Windows ARM64 VM can prove general
Windows behavior but cannot establish a native Windows x86_64 ABI or asset
claim, even when x86 emulation runs there. Release asset qualification keeps
that distinct architecture-specific boundary; both selected peers still verify
the same signed publication inventory independently. Project-453 macOS and
Windows review and protected runners must be admitted before the stricter graph
is landed or made a required remote check.

The native GitLab jobs now consume the existing `release_compatibility` Nox
session instead of repeating a Python test session. That session builds one
candidate, checks commands, loopback traffic and fresh lifecycle, then exercises
real predecessor upgrade and rollback. The Runner supplies immutable public
predecessor assets and an external trust anchor from its own GitLab publication
plane; source contains only destination-resolved input variable names. Missing
supply fails before building. Windows ARM64 remains an x64 process and asset
under emulation until the locked runtime and release inventory support ARM64. No
new release target is inferred from a Runner host name. The Windows account must
invoke x64 Mise because upstream selects lock architecture from its compiled
executable; an ARM64 Mise cannot consume the current `windows-x64` lock entries
by assumption.

Linux source jobs select an event-derived tag: merge requests use a low-trust
review capability; accepted `dev` uses a separate protected capability.
Accepted-source, promotion, and tag checks explicitly use the protected Runner.
Fleet admission must verify project locking, tagged-only scheduling,
`ref_protected` enforcement, and separate accounts and caches. YAML selectors
cannot establish those external facts. Local verification now covers 166 focused
contracts, the complete three-version Python graph, and 50 combined macOS native
cases including authentic predecessor upgrade and rollback. The native session
leaves only the original product watchdog and listener running. Official GitLab
dry-run validation accepts the nine-job dev graph without errors or warnings.
These results prove candidate source and local behavior, not Runner registration
or hosted execution; those remain unfinished until observed at the accepted
source.

At source `93aecba5`, GitHub Verify run `35885350727` executed its Windows
Server 2025 native asset job (45 passed, one skip), Python 3.12–3.14 jobs, and
published-predecessor compatibility. GitLab MR pipeline `8003` completed six
Linux ARM64 jobs on project runner `35`. Those are valid observations of the
earlier graph, not proof of the newly required peer-local three-OS graph.

### Evidence and documentation are reader paths, not residue stores

Current acceptance is reconstructed from exact Git state, test and quality
results, OpenSpec, ETHOS-selected Attestations, signed release assets, and
observed runtime state. A tracked `evidence/`, Claim, Chronicle, parity tree, or
records directory survives only with a current unique consumer and retention
contract. Historical explanation belongs in immutable OpenSpec archives,
Decision Records, Changelog, release records, or Git history.

Documentation follows reader intent: product overview, concepts, setup and
operations, architecture, contribution, governance, and decisions. Every content
filename names its subject; every directory index has a navigation job. Decision
Records use `dr-<sequence>-<subject>.md`. Examples are executable and
production-shaped, never toy placeholders. Prose, tables, commands, links, and
configuration are formatted and verified.

### SemVer and destructive retirement

`VERSION` is the sole release identity. Public incompatibility determines the
next SemVer value; internal restructuring alone does not force a major release.
The existing release-metadata owner binds `VERSION`, local product tags, and a
Keep a Changelog 1.1.0 document. It permits one current pending release during
release preparation, rejects every historical untagged heading, and requires
canonical change categories. Unpublished historical headings are folded into the
later tagged release that actually carried their changes, preserving the
user-visible account without preserving fictional releases. Published releases
are immutable. Merged proposal branches, failed unpublished intermediates,
retired Work Lanes, old hooks, orphaned runtimes, temporary services, caches,
and generated residue are removed once exact ownership and lack of consumers are
proved. Deletion is a first-class task, not deferred housekeeping.

## Risks / Trade-offs

- **The broad Change becomes an excuse for a patch too broad to review** → keep
  one Change but use ordered atomic commits, focused proofs, and task-level
  acceptance; never combine unrelated mutations in one commit.
- **Topology work destabilizes the working service** → preserve the accepted
  installed release until a signed candidate passes native lifecycle proof;
  source restructuring does not mutate the active service.
- **Strict quality expansion creates arbitrary vetoes** → every rule records
  risk, scope, measurement, false-positive cost, remediation, and review
  condition; unsupported or redundant rules are rejected rather than enabled for
  appearances.
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
3. Freeze product ontology and dependency directions, then migrate one domain at
   a time while deleting each superseded owner in the same atomic commit.
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
   artifacts, native test resources, caches, and records with no current
   consumer; then archive this Change and verify the repository family is
   terminal.
