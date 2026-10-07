# Tasks

## 1. Baseline and Authority

- [x] 1.1 Capture the exact Work Lane HEAD, tree, lease generation, active
      Change, installed release, listener, native service, local branches, both
      Forge refs, latest CI results, tags, Releases, and owned residue.
- [x] 1.2 Inventory every tracked file and generated projection by semantic
      owner, consumer, source-of-truth, reason to change, dependency direction,
      and retirement condition; verify no file is silently omitted or multiply
      owned.
- [x] 1.3 Map every public command, result, configuration field, environment
      variable, network route, native resource, release artifact, and
      documentation entrypoint to one product invariant and one authoritative
      implementation.
- [x] 1.4 Reconcile all active source, tests, OpenSpec, documentation, quality
      declarations, CI projections, and release metadata; record each
      contradiction as an explicit task in this Change rather than a parallel
      backlog.
- [x] 1.5 Prove the current installed release remains healthy and unchanged
      before source migration; save its exact version, executable digest,
      payload identity, service identity, listener PID, and loopback health as
      the rollback baseline.

## 2. Windows Native Environment and Immediate Release Safety

- [x] 2.1 Add RED contracts proving one native environment owner preserves
      arbitrary host execution state, removes inherited Proxy and Python
      injection state, redirects every product-owned root, and accepts an
      explicit empty product `PATH`.
- [x] 2.2 Implement `src/codex_responses_proxy/runtime/process_environment.py`
      as the sole semantic owner and verify its focused contracts on the current
      host.
- [x] 2.3 Make the release fixture and packaged CLI contracts consume the
      semantic environment owner; delete the duplicate Nox black-box runner,
      partial environment dictionaries, `SystemRoot` special case, and
      environment allow-list.
- [x] 2.4 Verify help, version, status, every public command, prewarm, and
      native lifecycle black-box paths use the same environment contract without
      Python discovery or host-substrate removal.
- [x] 2.5 Reproduce the former Windows `WinError 10106` boundary in a regression
      contract and obtain GREEN evidence from the real Windows native artifact
      job for the exact candidate commit.
- [x] 2.6 Verify macOS and Linux native acceptance remain green and no new
      service, process, temporary payload, cache, or host configuration survives
      either successful or failed execution.

## 3. Product Boundary and Public Interface

- [x] 3.1 Define the terminal product ontology for request admission, portable
      Responses semantics, Provider adaptation, transport, runtime
      configuration, payload generations, lifecycle transactions, native
      supervision, and CLI presentation; verify every public concept has one
      owner and no AIGW or client-control responsibility.
- [x] 3.2 Audit all CLI commands, options, defaults, exit codes, human output,
      JSON schemas, and help text against real user journeys; add RED tests for
      every ambiguous, inaccurate, over-broad, or misleading result.
- [ ] 3.3 Converge human and machine output on one typed result model with
      precise problem, current state, safe next action, and bounded evidence;
      verify no traceback, warning, private path, credential, payload, or
      internal module name leaks.
- [ ] 3.4 Verify `install`, `status`, `doctor`, `reload`, `rollback`, `recover`,
      and `uninstall` are semantically distinct, complete, symmetric, idempotent
      where declared, and free of hidden source or Forge dependencies.
- [x] 3.5 Remove parallel command, package, service, environment, port, release,
      and platform identities without conflating their owners.
- [ ] 3.6 Prove Proxy operates independently with an ordinary explicit upstream
      route and loopback endpoint; verify AIGW absence, client absence, and
      Forge absence do not prevent local product operation. Admit one non-Codex
      Responses client through real request, replay, streaming, error, and
      installed-client evidence before the planned major-version rename or a
      generic client-support claim.

## 4. Responses and Provider Architecture

- [ ] 4.1 Trace the complete request path from HTTP admission through schema
      classification, replay relationships, Provider projection, transport,
      streaming, response validation, and error recovery; verify each
      transformation has one typed input and output owner.
- [ ] 4.2 Merge parallel replay classifiers, provider-shape inference,
      sanitizers, and recovery predicates into one authoritative item and
      relationship policy; delete all fall-through and compatibility
      interpretations.
- [ ] 4.3 Add adversarial contracts for malformed containers, unknown item
      types, encrypted content, tool-call pairing, provider-local items,
      streaming control events, non-stream terminal responses, and structured
      Provider errors. Qualify model-visible image semantics and recovery of the
      affected historical conversation at its actual selected endpoint. Preserve
      ciphertext without claiming cross-provider decryptability or attributing a
      pre-tool Agent failure to Proxy without route evidence.
- [x] 4.4 Ensure Provider-specific wire differences live only in narrow adapters
      selected from one manifest and policy contract; verify generic relay,
      lifecycle, CLI, and tests do not branch on Provider names.
- [x] 4.5 Define the low-cost Provider extension path—manifest entry, adapter,
      policy, contract fixtures, conformance suite, documentation, and no core
      modification—and prove it with one representative non-default Provider
      fixture.
- [ ] 4.6 Evaluate mature local-first gateways and protocol libraries against
      the exact retained differentiators; replace custom generic mechanics only
      where doing so reduces source, dependencies, runtime risk, and maintenance
      authority.
- [ ] 4.7 Verify request and response performance, bounded retries, cooldown
      monotonicity, cancellation, connection reuse, memory, and streaming
      latency against explicit budgets without weakening correctness or
      multiplying retries. Qualify original-thread replay and compaction
      separately from local framing, retry, and release tests.
- [ ] 4.8 Admit the standard role/content Responses message without an explicit
      `type` through the shared item policy, without accepting unknown replay
      shapes. Qualify the published release through the Hermes consumer.

## 5. Native Lifecycle and Resource Ownership

- [ ] 5.1 Converge install, upgrade, reload, rollback, recovery, and uninstall
      on one transaction state machine and mutation lock; verify preconditions,
      durable transitions, and terminal states through failure injection,
      including same-controller cleanup retry and cross-process recovery after
      partial directory removal.
- [ ] 5.2 Make payload generation, manifest, command projection, transaction
      journal, rollback snapshot, service declaration, listener, watchdog, and
      handoff child each have exact ownership identity and one cleanup owner.
- [ ] 5.3 Bind macOS supervision to the native user Background domain; prove
      exact legacy GUI migration, unique registration, predecessor exit and
      successor identity. Observe registered services even without a carrier;
      conserve both domains, disabled overrides, and unrelated plist bytes.
      Prior GUI-only evidence does not qualify this boundary. Qualify the paired
      native predecessor and old-producer recovery journeys in task 9.12.
- [x] 5.4 Prove Linux systemd behavior on a real supported user service and in
      the declared container boundary, including explicit behavior when no user
      bus exists; remove session-only fallback processes.
- [x] 5.5 Prove current-user Windows Task Scheduler install, status, handoff,
      recovery, rollback, uninstall, command projection, and process-generation
      ownership from the native artifact.
- [ ] 5.6 Verify bounded teardown after success, assertion failure, exception,
      timeout, and interruption on every supported platform; compare exact owned
      services, processes, journals, payloads, commands, and temporary files
      before and after, preserving unrelated canonical installations.
- [x] 5.7 Verify active-target installation is a true no-op, failed successor
      transition restores the exact predecessor, repeated recovery is terminal,
      and uninstall preserves all unowned content.
- [ ] 5.8 Remove legacy payload shapes, alternate launchers, obsolete journals,
      dead schema readers, compatibility branches, and fallback service
      identities after the terminal lifecycle proves no consumer.
- [x] 5.9 Preserve request admission during capability-qualified upgrade and
      rollback handoff; prove concurrent new requests and in-flight responses
      complete without `proxy_draining`, while retaining the bounded legacy
      native-generation fallback.

## 6. Semantic and Physical Repository Topology

- [ ] 6.1 Derive the target package map from the product ontology and
      repository-only domains; verify every package name is precise,
      non-overlapping, and explains its dependency direction without reading
      implementation details.
- [ ] 6.2 Replace flat suffix families and ambiguous buckets in `src`, `tests`,
      and `tools` with semantic subpackages; specifically converge
      `tools/release/publish*`, `publication/*`, and `forge/*` on one
      publication entrypoint, release construction owner, and Forge adapter
      boundary.
- [ ] 6.3 Remove or precisely rename every ambiguous `common`, `shared`,
      `utils`, `helpers`, `misc`, `base`, `manager`, generic `service`,
      concatenated compound, and implementation-shaped module; verify no
      compatibility import or re-export remains.
- [ ] 6.4 Make tests mirror product and repository-tool semantics rather than
      implementation filenames; keep unit tests with their domain and isolate
      integration, native, release, and end-to-end contracts by evidence scope.
- [ ] 6.5 Establish one-way import rules for product domains and repository
      tools, detect cycles and undeclared owners, and verify no product package
      imports tests, repository tooling, Forge code, or ETHOS internals.
- [ ] 6.6 Audit `.config`, root files, OpenSpec, docs, schemas, workflows,
      generated files, and release assets for the same semantic and physical
      isomorphism; relocate, absorb, rename, or delete every
      mixed-responsibility carrier.
- [ ] 6.7 Remove empty packages, redirect-only indexes, dead entrypoints,
      duplicate schemas, parallel constants, obsolete fixtures, unused
      dependencies, and unreachable code; verify repository size and entity
      count decrease without losing a required invariant.

## 7. Quality System

- [x] 7.1 Replace scattered quality declarations with one responsibility map
      that positively covers every tracked carrier and names the mature tool or
      product-semantic checker that owns each concern.
- [ ] 7.2 Consolidate Ruff formatting, imports, correctness, modernization,
      naming, documentation, exception, logging, security, complexity, pytest,
      and dead-code rules into one comprehensible authority; enable every
      applicable rule and justify every inapplicable rule without blanket
      ignores.
- [ ] 7.3 Make Ty strict at product and repository-tool boundaries, narrow
      unions and protocols, eliminate avoidable `Any`, and add typed adapters
      where external data enters; verify no unresolved type warning is accepted.
- [ ] 7.4 Adopt or fully exercise mature tools for dependency hygiene, dead
      code, security, Markdown format and lint, links, TOML, YAML, JSON, CUE,
      Actions, secrets, licenses, SBOM, and vulnerabilities; delete custom
      equivalents that add no unique semantic value.
- [ ] 7.5 Close structural measurement and enforcement together: verify
      file/function ELOC, logical statements, nesting and complexity semantics;
      classify the native-rule findings by product, tooling and test behavior;
      set risk-justified blocking limits, remove the observation-only acceptance
      contract, and simplify each affected semantic owner without suppressions
      or shallow extraction.
- [ ] 7.6 Enforce public API and repository-tool docstrings while excluding
      ornamental test docstrings; verify documentation signatures and
      implementation signatures cannot drift.
- [ ] 7.7 Make warnings fatal across tests, builds, docs, tools, native
      binaries, and CI; remove every known warning at its owner rather than
      filtering or baseline-suppressing it.
- [ ] 7.8 Verify commit subjects through one scoped Conventional Commit grammar
      in local hooks and both Forge paths, including generated lifecycle
      commits, with no duplicate parser or historical exception list.
      Distinguish tip-only checks from introduced-range acceptance; qualify
      actual hosted event-range and signature enforcement without inferring an
      unknown range from a zero baseline.
- [ ] 7.9 Run formatter, linter, type, architecture, dependency, security,
      documentation, configuration, and focused behavior gates on the migrated
      tree; require pristine output before the full suite.
- [ ] 7.10 Prove control effectiveness with isolated conformance cases for
      native tool settings, scope inclusion, nonzero exits, local entrypoints
      and hooks, and every CUE event route; a missing tool, skipped required
      check, empty scope or stale report must not establish acceptance. Qualify
      cold full-suite prerequisite ordering, installed ETHOS semantic and
      diagnostic evidence, and every required native platform path.
- [ ] 7.11 Reconcile the quality responsibility map with actual coverage,
      dependency, dead-code, security, documentation and delivery checks; close
      product/tooling/orchestration coverage independently, remove duplicate
      custom checkers, and leave unverified claims open.
- [x] 7.12 Eliminate current canonical OpenSpec INFO length findings by
      splitting oversized requirements at semantic boundaries without dropping
      obligations or scenarios; require official strict validation with no
      issues before exact-HEAD proof.

## 8. Development Environment and Supply Chain

- [x] 8.1 Define `mise` as the sole cross-platform developer entrypoint and
      provide minimal `bootstrap`, `check`, `native`, and `release` tasks that
      call existing ecosystem owners rather than shell wrappers.
- [ ] 8.2 Prove a clean Work Lane reconstructs independent `.venv`, `.nox`,
      `node_modules`, build, coverage, and temporary state from locks while
      sharing only content-addressed mise, uv, npm, and Python caches.
- [ ] 8.3 Remove ambient interpreter, user-site, global mise configuration,
      system package, and another repository environment from local and hosted
      success paths; verify empty-HOME and empty-project-cache bootstrap.
- [ ] 8.4 Online-audit every direct runtime, development, OpenSpec, Python,
      Node, mise, uv, Nox, packaging, documentation, CI Action, and release
      dependency; advance each to its latest compatible stable version in the
      existing SSOT.
  - [ ] 8.4.1 Refresh the current stable Python, uv, Mise, Cyclopts, filelock,
        Ruff, and `virtualenv` pins through their existing authorities. Preserve
        Python 3.12 compatibility, eight-platform artifact provenance, the npm
        closure, and the running service. Require byte-clean repeat resolutions,
        full source checks, cold development, exact-HEAD proof, and every
        declared hosted source job before calling the refreshed toolchain
        qualified.
- [x] 8.5 Regenerate `mise.lock`, `uv.lock`, and `package-lock.json`
      deterministically; verify a second resolution is byte-clean and no
      duplicate version literal controls behavior.
- [ ] 8.6 Configure one dependency update proposal owner with release-age
      policy, grouping, vulnerability priority, auto-merge criteria, and
      dual-Forge projection; verify it cannot open competing GitHub and GitLab
      updates for the same change.
- [ ] 8.7 Produce and verify SBOM, vulnerability, license, checksum, signature,
      and provenance outputs from the exact locked candidate without embedding
      checkout paths, timestamps, credentials, or installer metadata.
- [ ] 8.8 Evaluate PyInstaller and current alternatives against startup, size,
      reproducibility, platform support, lifecycle integration, and maintenance
      cost; retain or replace it based on measured total value, then delete the
      rejected path.

## 9. CI and Forge Projection

- [ ] 9.11 Replace repeated GitLab Mac/Windows Python sessions with the existing
      native lifecycle and real-predecessor session, isolate Linux review and
      protected routes, verify generated projections and negative contracts, and
      admit and execute the exact-source Runner jobs. Bind unchanged main
      promotion to separately observed proof of the exact accepted dev object;
      reject different OIDs even with equal trees. Select protected tag native
      jobs only after the exact tag identity and signature prerequisite, without
      duplicating the product graph on main or replacing platform evidence with
      metadata. Qualify the real Windows locked-generation case and original
      transactional journey with bounded retry, file/ancestor/digest
      revalidation, unchanged permissions, and retained persistent-error
      recovery authority. Qualify a short, isolated Runner-supplied native TEMP
      input and child temporary variables bound to the same owned root.
- [ ] 9.12 Qualify the paired native journeys in 5.3: untouched published
      predecessor payload through current-control upgrade and rollback, and
      unchanged old-CLI-produced recovery input through current public recovery.
      Prove complete payload identity, bounded old-controller process exit,
      public-operation cleanup before fallback teardown, and host conservation.
      Admit selector, snapshot, command ownership, and exact native identity
      before disposal; failed Windows queries remain unknown. Verify both
      documented not-found HRESULT values while preserving refusal of access,
      service, malformed XML, and timeout results. Qualify current-user session
      applicability and complete native macOS and Windows matrices; do not
      provision a GUI to satisfy an obsolete predecessor installer criterion.
      Preserve original pipeline failures.
- [ ] 9.1 Define the complete CI graph in CUE—quality, Python matrix, native
      assets, platform lifecycle, release metadata, publication, and parity—with
      explicit facts proved by each job. Qualify the affected Python-only native
      jobs without importing unrelated Node-dependent governance cases or adding
      an unrelated runtime.
- [ ] 9.2 Generate GitHub Actions and GitLab CI from the CUE model, verify
      semantic parity and provider-specific deltas, and reject hand-edited
      projection drift.
- [ ] 9.3 Cover proposal creation and update, review SHA, maintainer
      fast-forward, `dev`, `main`, and tag events; verify every admissible
      integration path triggers the required exact-SHA evidence.
- [ ] 9.4 Separate independent jobs for fast quality, Python 3.12/3.13/3.14
      compatibility, macOS, Linux, Windows, release construction, and
      publication; remove monolithic verification and meaningless duplicate
      runs. Qualify job- and matrix-scoped uv cache ownership through actual
      hosted execution.
- [ ] 9.5 Define when exact-SHA evidence may be reused and when platform,
      environment, source, lock, or release changes require new execution;
      verify reuse cannot turn stale or partial proof green.
- [ ] 9.6 Require each selected Forge to execute the same macOS, Linux, and
      Windows functional proof semantics at the exact revision; qualify
      project-local runner admission before making the stricter graph required.
      Keep Windows ARM64 functional evidence distinct from native x86_64 ABI
      proof.
- [ ] 9.7 Verify GitHub and GitLab authentication, SSH agent, author identity,
      commit signature, tag signature, protected-branch, proposal-branch, and
      automatic merge behavior without password prompts or private-key mutation.
      Repair only owner-confirmed historical committer aliases through accepted
      ETHOS. Preserve authors, other contributors, message bytes, timestamps,
      trees, and ordered parents; verify actual peer attribution.
- [ ] 9.8 Ensure proposal branches are unprotected, merge automatically after
      required evidence for the maintainer policy, and are deleted on merge;
      verify no remote `work/*` or stale proposal remains.
- [x] 9.9 Run both generated CI projections for the exact candidate and verify
      `dev`, `main`, and the final tag receive the intended green graph with
      readable, bounded job output.

## 10. Release and Installed Product Proof

- [ ] 10.1 Determine the next version from actual public compatibility, update
      sole-owner `VERSION`, package metadata, Changelog, documentation, and
      asset naming, and verify strict SemVer and Keep a Changelog consistency.
  - [ ] 10.1.1 Qualify current Changelog navigation and native peer locators
        after absorption of the signed product-owner source. Preserve every
        historical entry, verify neutral headings and both actual destinations,
        and keep SemVer, YANKED, current locks, and three-platform CI
        responsibilities intact. Qualify source navigation, accepted
        integration, and publication separately.
  - [ ] 10.1.2 Qualify the accepted installed ETHOS identity/reference contract,
        reject reachable wrong-repository targets, and reconcile historical peer
        tag differences through its authorized repair contract. Verify each
        peer's actual result without a private map or duplicate checker.
- [ ] 10.2 Build reproducible macOS, Linux, and Windows native bundles from the
      locked candidate; verify contents, modes, manifests, checksums,
      signatures, SBOM, provenance, and common-platform byte identity where
      applicable.
- [x] 10.3 Verify release source is clean, signed, exact-HEAD proved and
      immutable, with current source-acceptance authority, before creating one
      signed annotated tag object. Delivery-inclusive Change obligations stay
      open until observed; archive is not a prerequisite for their release
      input.
- [x] 10.4 Project the same signed commit and tag objects to each selected Forge
      through independent exact-CAS operations; verify no author, committer,
      parent, tree, message, or signature rewriting.
- [x] 10.5 Publish complete matching Release inventories on GitHub and GitLab;
      independently verify byte digests, signatures, trust anchors, metadata,
      and user-facing link identity from fresh persisted state, including
      idempotent and concurrent publication paths.
- [x] 10.6 Upgrade the preserved working installation from the previous accepted
      release, prove runtime health and active-target no-op, roll back, recover,
      re-upgrade, uninstall, and reinstall using only published artifacts.
- [x] 10.7 Verify installed status reports exact release, payload, manifest,
      service, process, listener, command projection, and transaction state
      without consulting source, Git, uv, Nox, ETHOS, or a Forge.

## 11. Documentation, Configuration, and Experience

- [ ] 11.1 Rebuild the documentation map around product overview, concepts,
      setup, operations, architecture, contribution, governance, and decisions;
      verify every canonical document is reachable from `docs/README.md` and
      every index has a navigation purpose.
- [ ] 11.2 Rewrite installation, status, diagnostics, update, rollback,
      recovery, uninstall, Provider routing, native platform, and
      troubleshooting journeys against the released executable; execute every
      documented command in a clean environment.
- [ ] 11.3 Normalize names, headings, terminology, tables, code blocks, internal
      links, and external links for semantic precision and readable fidelity,
      clarity, and elegance; verify Markdown format, lint, table, and link gates
      are clean.
- [x] 11.4 Rename Decision Records to `dr-<sequence>-<subject>.md`, complete the
      decision register, and add only decisions that explain enduring product
      boundaries or rejected alternatives.
- [ ] 11.5 Audit `.editorconfig`, `.gitattributes`, `.gitignore`, `.npmrc`,
      pytest, pyproject, mise, uv, OpenSpec, ETHOS adoption, release, and
      quality configuration; make each field reside in its true tool authority
      and delete stale or duplicate entries.
- [ ] 11.6 Remove toy examples, private workstation paths, stale versions,
      obsolete commands, WCP references, AIGW coupling, empty evidence shells,
      claims, chronicles, parity directories, and historical instructions from
      current reader paths.
- [ ] 11.7 Verify source, config, specs, docs, help, schemas, generated
      workflows, and release metadata use the same public vocabulary and that a
      renamed concept leaves no stale reference.

## 12. Performance, Security, and Operational Reliability

- [ ] 12.1 Benchmark startup, steady request latency, streaming first-event
      latency, memory, concurrency, handoff interruption, install, update,
      rollback, and recovery using reproducible inputs; establish risk-derived
      budgets.
- [ ] 12.2 Profile hot paths and remove accidental allocations, repeated
      parsing, redundant serialization, duplicate network work, polling churn,
      and unnecessary subprocesses without changing portable semantics.
- [ ] 12.3 Threat-model local listener exposure, upstream credentials, request
      and response logging, temporary assets, signature trust, update supply
      chain, native service ownership, and transaction recovery; close every
      high-severity gap.
- [ ] 12.4 Verify logs are structured, bounded, redacted, rotation-aware, and
      operationally useful; introduce no logging framework unless it replaces
      more complexity than it adds.
- [ ] 12.5 Inject network failure, malformed Provider response, interrupted
      handoff, killed controller, disk error, locked Windows file, stale
      service, PID reuse, and invalid journal; verify bounded failure and exact
      recovery without data or host pollution.

## 13. Destructive Cleanup and Terminal Closeout

- [ ] 13.1 Delete every superseded module, test helper, configuration owner,
      schema, workflow fragment, document, compatibility path, alias, fallback,
      exemption, baseline, and dependency identified by the ownership inventory;
      verify no tracked reference or runtime consumer remains.
- [ ] 13.2 Remove exact orphaned test services, processes, plists or service
      entries, transaction roots, payloads, hooks, caches, bytecode, coverage,
      build output, temporary files, and stale ETHOS projections without
      touching user data or foreign state.
- [ ] 13.3 Merge or discard every local and remote proposal according to
      semantic value, delete merged proposal and remote `work/*` refs, retire
      obsolete Worktrees and leases, and verify only canonical repository-family
      members remain.
- [ ] 13.4 Remove failed unpublished tags, draft Releases, duplicate assets, and
      unreferenced records from both Forges and local storage while preserving
      formal immutable release history and required recovery evidence.
- [ ] 13.5 Freeze the complete candidate and run strict OpenSpec validation, all
      focused gates, full quality, Python matrix, three-platform native
      acceptance, reproducible build, security, performance, documentation, and
      repository-residue audits exactly once at final scope. Require accepted
      installed ETHOS proof, applicable same-attempt diagnostics, both Forge
      platform matrices, and current release inputs; retain original failed
      receipts until their consumer releases them.
- [ ] 13.6 Complete every task from evidence, archive this Change through the
      current ETHOS public command, land the signed candidate, synchronize local
      `main/dev` and both Forge `main/dev`, and verify final tag CI and Releases
      are green and identical where required.
- [ ] 13.7 Prove the final installed product and clean repository family satisfy
      every modified capability, disclose any genuinely unverified external
      fact, and retain no active Change, Work Lane, proposal branch, temporary
      authority, or entity with no current consumer.
