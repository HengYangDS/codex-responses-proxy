# Tasks

## 1. Baseline and Authority

- [x] 1.1 Capture the exact Work Lane HEAD, tree, lease generation, active
      Change, installed release, listener, native service, local branches, both
      Forge refs, latest CI results, tags, Releases, and owned residue. Baseline
      source 71639365 retains tree 246577eb after correcting the unpublished
      commit scope; its lease generation is 8 and the active Change is
      terminal-product-convergence. Local main/dev/candidate and both peer
      main/dev remain c20b086e; v4.0.1 is tag object 7f554098. Both peers
      main/dev/tag CI pass, both Release inventories contain eight named product
      assets, and no remote proposal/work ref remains. Installed 4.0.1 verifies
      all 86 payload files, listener 65593 accepts without draining, supervisor
      65714 owns the sole canonical LaunchAgent, and rollback 4.0.0 is
      available. Raw observations are under
      `build/verification/71639365d4869511f02cc683cdcd14f27f333d12/` and the
      unchanged-source baseline under
      `build/verification/fdc9f5ab9c15614642b0347f7c9d37d2b1a17e11/`. This is a
      captured baseline, not fresh release-asset byte verification or final
      residue retirement.
- [x] 1.2 Inventory every tracked file and generated projection by semantic
      owner, consumer, source-of-truth, reason to change, dependency direction,
      and retirement condition; verify no file is silently omitted or multiply
      owned. The existing responsibility map now carries the complete lifecycle
      contract for each of its 17 non-overlapping semantic roles rather than
      introducing a second inventory. Its native audit assigns all 1,212 tracked
      carriers exactly once and rejects any role missing owner, consumer,
      source-of-truth, change condition, dependency direction, or retirement
      condition. The focused suite passes 43 tests; Ruff and Taplo validate the
      changed Python and TOML carriers.
- [x] 1.3 Map every public command, result, configuration field, environment
      variable, network route, native resource, release artifact, and
      documentation entrypoint to one product invariant and one authoritative
      implementation. The existing controlled-value policy now maps all nine
      public surface classes to exactly one of 15 authoritative controls and
      records the invariant protected by every control. Its audit rejects
      missing invariants, malformed or unknown surfaces, duplicate surface
      owners, and any unowned public surface. The focused suite passes 31 tests;
      Ruff and Taplo validate the changed Python and TOML carriers.
- [x] 1.4 Reconcile all active source, tests, OpenSpec, documentation, quality
      declarations, CI projections, and release metadata; record each
      contradiction as an explicit task in this Change rather than a parallel
      backlog. Strict OpenSpec and the repository governance graph pass at
      source `316b9daf`; release metadata agrees on 4.0.3 and both Forge
      projections agree with the CUE owner. Remaining contradictions are
      retained only in their existing executable tasks: generic or misplaced
      source and test ownership in 3.1 and 6.1-6.4; incomplete CLI/result and
      runtime-setting documentation in 3.2-3.5 and 11.1-11.7; unresolved replay,
      Provider, and performance boundaries in 4.1-4.7 and 12.1-12.5; incomplete
      resource teardown in 5.1-5.2 and 5.6; unfinished quality enforcement in
      7.2-7.11; clean-lane bootstrap and dependency automation in 8.2-8.3 and
      8.6-8.8; CI admission and branch policy in 9.1-9.8; final artifact and
      publication proof in 10.2 and 13.4-13.7; and tracked or host residue in
      13.1-13.3. No parallel backlog or second status authority was added.
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
      owner and no AIGW or client-control responsibility. The existing
      architecture policy now binds all nine concepts to distinct existing
      product modules and declares Provider selection, credentials, client
      configuration, model selection, and conversation history as external
      responsibilities. The topology audit rejects reused, missing, or
      out-of-product concept owners; focused structure and governance validation
      passes 71 tests and 24 subtests without adding another ontology carrier.
- [x] 3.2 Audit all CLI commands, options, defaults, exit codes, human output,
      JSON schemas, and help text against real user journeys; add RED tests for
      every ambiguous, inaccurate, over-broad, or misleading result. Direct
      source invocation exposes exactly `install`, `status`, `doctor`,
      `recover`, `reload`, `rollback`, and `uninstall`; every subcommand help,
      default port, lifecycle deadline, JSON switch, required asset/trust input,
      purge option, invalid port, and missing rollback target was exercised. The
      full CLI contract suite passes 65 tests and five subtests with five
      native-distribution cases intentionally left to the release scope. The
      installed 4.0.3 `status --json` and `doctor --json` remain healthy. No
      product defect was inferred from the initially malformed shell invocation.
- [ ] 3.3 Converge human and machine output on one typed result model with
      precise problem, current state, safe next action, and bounded evidence;
      verify no traceback, warning, private path, credential, payload, or
      internal module name leaks. Native error leakage and unexpected tracebacks
      have RED/GREEN coverage. One typed success/failure outcome now rejects
      incomplete command results before either projection. Doctor now preserves
      degraded and invalid states with categorical, path-free checks and
      matching human/JSON next actions. A subsequent result-integrity audit
      reproduces 14 false-success cases for zero, negative or unchanged reload
      process IDs and negative cleanup counts. The existing outcome owner now
      rejects these contradictions while preserving legitimate zero-process
      cleanup; 143 sibling CLI cases and five subtests pass, including
      controller-recovered reload. The final full graph passes 1,914 cases per
      Python 3.12/3.13/3.14 with all 1,220 tracked hashes conserved. The final
      native suite passes 49 cases plus one Linux-only skip, including authentic
      4.0.4 upgrade and rollback; production process generations, registrations,
      overrides and plist hashes are conserved and owned scratch is absent. Peer
      acceptance and formally distributed ETHOS proof remain open. Evidence:
      `build/verification/native-supply-gitlab-20261001/public-outcome-identity-*`.
      Initial installation and compensation failures now remain separately
      visible, with bounded native error codes and no false recovery-write
      claim. Source regressions pass; the actual Windows generation-removal
      cause and native successor qualification remain open. Evidence:
      `build/verification/installation-failure-context-13aaf199/`.
- [ ] 3.4 Verify `install`, `status`, `doctor`, `reload`, `rollback`, `recover`,
      and `uninstall` are semantically distinct, complete, symmetric, idempotent
      where declared, and free of hidden source or Forge dependencies.
- [x] 3.5 Remove parallel command, package, service, environment, port, release,
      and platform identities without conflating their owners.
      `product_identity.py` owns public product identity and released platforms;
      `runtime/config.py` owns the port; release job names in the GitHub
      observer remain independent acceptance requirements, not a second CI
      projection. The controlled-value audit passes with no errors, its 31
      contracts pass, and product source contains no duplicate provider or
      product identity literal outside its owners.
- [ ] 3.6 Prove Proxy operates independently with an ordinary explicit upstream
      route and loopback endpoint; verify AIGW absence, client absence, and
      Forge absence do not prevent local product operation. Admit one non-Codex
      Responses client through real request, replay, streaming, error, and
      installed-client evidence before the planned major-version product rename
      or a generic client-support claim.

## 4. Responses and Provider Architecture

- [ ] 4.1 Trace the complete request path from HTTP admission through schema
      classification, replay relationships, Provider projection, transport,
      streaming, response validation, and error recovery; verify each
      transformation has one typed input and output owner.
- [ ] 4.2 Merge parallel replay classifiers, provider-shape inference,
      sanitizers, and recovery predicates into one authoritative item and
      relationship policy; delete all fall-through and compatibility
      interpretations. Named later tool deliveries now share one relationship
      decision across projection, diagnostics and recovery. Four focused RED
      cases and two installed-4.0.1 native RED cases reproduce the former
      rejection; the repaired source passes 315 protocol/relay/provider tests
      and 172 subtests. A read-only 923-item reconstruction of the affected
      conversation preserves both later deliveries and is projection-idempotent.
      Evidence:
      `build/verification/24d0e9f7e9be0b1d494da2402c82748001cd6862/async-*`. The
      macOS 4.0.2 native candidate passes all 40 CLI/subprocess contracts,
      including both formerly failing delivery cases, without registering a
      service or changing the healthy formal 4.0.1 listener. The complete source
      graph passed on Python 3.12/3.13/3.14; a subsequent
      distinct-output-identity boundary was then added and verified by focused
      tests and this native build. The final signed commit `b18deb14` passes
      full proof `fef10908`; both peer main/dev and signed tag `v4.0.2` identify
      the same objects and all accepted/ref/tag pipelines pass. Both formal
      Releases contain the same eight verified signed assets, and both proposal
      refs are absent. The downloaded macOS artifact passes 43 CLI/subprocess
      and native helper cases; the final authentic predecessor journey passes
      separately after the combined runner reached its caller-owned deadline.
      Production upgrades to 4.0.2 at listener 12599, retains 4.0.1 rollback,
      passes all six doctor checks and active-target no-op, and preserves 37
      protected files plus runtime/provider settings. Both predecessor processes
      exit; exact test scratch, suffixed services and plists are removed.
      Evidence: `build/verification/b18deb14ef1deca3a42587b3bc53b5b3f1aad7b6/`.
      The original failing thread `01a02017` then continued successfully,
      explicitly consumed its historical async deliveries, and returned without
      `duplicate_output`; no session history or model state was changed.
- [ ] 4.3 Add adversarial contracts for malformed containers, unknown item
      types, encrypted content, tool-call pairing, provider-local items,
      streaming control events, non-stream terminal responses, and structured
      Provider errors. Release 4.0.0 preserves inline PNG/JPEG/WebP/GIF bytes,
      detail, order, image-only messages and paired tool results through the
      shared projection and classified retries. The original correction has 21
      RED cases, 31 passing content cases, 287 protocol/relay/provider tests
      with 174 subtests, and an independent 28-case probe. These semantics are
      now in the verified installed artifact; model-visible pixel acceptance and
      the remaining adversarial audit stay open. The encrypted-delegation
      incident is separately reproduced: an actual NEW_TASK message lost its
      ciphertext while the visible routing envelope was accepted. The repair
      preserves native encrypted agent envelopes and prevents shrinking recovery
      from dropping them. Six projection RED cases and a recovery RED case now
      pass. One bounded, noninteractive UCloud inference probe with the original
      encrypted task returns HTTP 200/completed and identifies the otherwise
      invisible review topic and path; no credential is printed or persisted.
      The updated macOS native asset passes all 40 CLI/subprocess contracts,
      including exact encrypted-envelope preservation. Signed 4.0.2 is now
      published on both peers and installed with successful native, doctor and
      protected-state acceptance. The existing `team_pilot_review` child then
      received a bounded nonempty read-only task and returned five relevant
      findings from the requested team-acceptance and lifecycle record. This
      proves meaningful task reception/completion; its requested exact marker
      was not echoed, so exact marker fidelity is not claimed. Preserving
      ciphertext is not a claim of cross-provider decryptability. At signed HEAD
      `8039417d`, the real loopback rejection contract also records
      `provider_bound_encrypted_content` without retrying or discarding the
      task; 57 relay/recovery tests and 47 subtests pass. The current
      DMXAPI-selected historical thread still fails; recovery of that
      conversation and full release acceptance remain open. Evidence:
      `build/verification/2ab49b21f2b2b589e8414996d01cb6db091e6ebc/encrypted-*`.
      October 1 native envelope inspection finds six of seven DDWG children
      failing before their first tool call. Their inherited histories contain
      234 plain messages and no encrypted function outputs; all seven receive a
      native encrypted task, including the successful child. Nine current
      encrypted-task preservation tests pass. Exact transmitted endpoints were
      not captured; current direct UCloud configuration does not prove Proxy
      participation. No task payload, history or model was rewritten. Metadata
      evidence: `subagent-decode-shapes-20261001.json` under
      `build/verification/a36a45c965b08a0ebff0650518f190641f906e5c/`.
- [x] 4.4 Ensure Provider-specific wire differences live only in narrow adapters
      selected from one manifest and policy contract; verify generic relay,
      lifecycle, CLI, and tests do not branch on Provider names. The product
      source and test control flow contain no Provider-name branch; the manifest
      selects the optional pure wire policy.
- [x] 4.5 Define the low-cost Provider extension path—manifest entry, adapter,
      policy, contract fixtures, conformance suite, documentation, and no core
      modification—and prove it with one representative non-default Provider
      fixture. `new-gateway` passes the real loopback Responses path;
      manifest-only and optional-policy fixtures and `CONTRIBUTING.md` describe
      the same extension contract. The focused suite passes 23 tests and 57
      subtests.
- [ ] 4.6 Evaluate mature local-first gateways and protocol libraries against
      the exact retained differentiators; replace custom generic mechanics only
      where doing so reduces source, dependencies, runtime risk, and maintenance
      authority.
- [ ] 4.7 Verify request and response performance, bounded retries, cooldown
      monotonicity, cancellation, connection reuse, memory, and streaming
      latency against explicit budgets without weakening correctness or
      multiplying retries. Released and installed 4.0.0 classifies decoded SSE
      data: comments, heartbeats and terminal markers preserve pre-content retry
      admission; only output-free `server_error` reuses the existing bounded
      budget. Committed output, tool calls, permanent errors and unknown
      failures are never replayed. The formal macOS artifact passes the
      failed-then-completed loopback regression with identical upstream request
      bytes and one visible result; diagnostics retain classification and
      bounded request UUIDs, not upstream prose. Original-thread replay and
      compaction remain unverified. The original Azure frames were unavailable,
      so this independently reproduced defect is not asserted to be their sole
      cause. Formal evidence:
      `build/verification/a3ef6f7e93ed491ecc6da653eeb5ba6ad59502e0/formal-stream.xml`.
      The current semantic audit reproduces seven finality/resource failures and
      a real held-open chunked-stream timeout before repair. The existing relay
      now consumes available HTTP bytes with native read1, finishes on the first
      response terminal, closes every upstream attempt in finally, and preserves
      post-commit failure as truncated HTTP instead of appending a second 503 or
      successful chunk terminator. The empty ResponseLike protocol is removed.
      All 51 SSE/loopback contracts pass; the full Python 3.12/3.13/3.14 graph
      passes 1625 tests per interpreter, with five native-only skips and 27
      separately selected contracts. Coverage is 97.81% statements and 95.49%
      branches. The rebuilt macOS arm64 asset passes all 38 CLI/subprocess
      cases, including closed, held-open and malformed streams through the
      actual listener; no native case skips. Host-projection preservation
      fixtures pass and the production 4.0.0 listener remains PID 6678.
      Evidence:
      `build/verification/f20c7e73107f1b1aaacff7bdf7c2d8eb781d185b/stream-*`.
      Signed 8e1ba4c5 now has full proof 1f4d7053, green GitHub review
      35020536925 and GitLab 6795, and identical local/peer main and dev. PR 47
      and MR 65 are merged without rewriting the object; both proposals are
      absent. Accepted GitHub main/dev 35022108202/35022108111 and GitLab
      6798/6797 pass. Hosted Windows native acceptance reports 43 passed and one
      platform-specific skip; all three native assets, retained-predecessor
      compatibility and Linux systemd lifecycle pass. The signed 4.0.1 release
      at c20b086e has exact full proof 6b87e51a and identical local/peer main
      and dev. PR 48/MR 66 are merged; both proposals are absent. Tag object
      7f554098 is identical on both peers, GitHub tag run 35023933368 and GitLab
      6802 pass, and all eight signed release files match after independent
      publication downloads. The formal macOS bytes pass the authentic published
      4.0.0 upgrade/rollback journey and closed/held-open/malformed stream cases
      (four tests). Production upgrades through the native admission-preserving
      handoff to 4.0.1 at PID 65593; predecessor 6678 exits, doctor is healthy,
      no transaction remains, repeated install is unchanged, and all 37
      protected file hashes remain equal. Rollback 4.0.0 and the canonical
      watchdog are retained. Evidence:
      `build/verification/c20b086e9095d0666ab194a886eb320434a265d3/`. Real
      historical-thread replay and broader performance/cancellation obligations
      remain open.
- [ ] 4.8 Admit the standard role/content Responses message without an explicit
      `type` through the shared item policy, without accepting unknown replay
      shapes. Source RED/GREEN, diagnosis, local HTTP loopback, and the 41-test
      native candidate suite pass. Published-release Hermes acceptance remains
      open.

## 5. Native Lifecycle and Resource Ownership

- [ ] 5.1 Converge install, upgrade, reload, rollback, recovery, and uninstall
      on one transaction state machine and mutation lock; verify preconditions,
      durable transitions, and terminal states through failure injection,
      including same-controller cleanup retry and cross-process recovery after
      partial directory removal.
- [ ] 5.2 Make payload generation, manifest, command projection, transaction
      journal, rollback snapshot, service declaration, listener, watchdog, and
      handoff child each have exact ownership identity and one cleanup owner.
      The macOS carrier audit reproduces symbolic-link target overwrite and
      acceptance of a mismatched label/executable outside this installation.
      Safe owned-file I/O now rejects indirect or unowned carriers before
      service mutation, persists atomically and rechecks unchanged teardown
      bytes. Label, watchdog arguments, home, native generation and environment
      injection have falsifying cases; legitimate filesystem aliases remain
      owned. Permission-denied metadata cannot become false absence. Every
      temporary supervision context now owns its platform-native paths rather
      than borrow a foreign absolute fixture root. Focused validation passes 320
      cases and 57 subtests. The final full source graph passes 1,866 cases per
      Python 3.12/3.13/3.14; all 1,220 tracked file hashes remain unchanged. The
      final native suite passes 49 cases with one Linux-only skip, including
      authentic published 4.0.4 upgrade and rollback in its supported GUI
      context. Canonical process generations, registrations, overrides and plist
      hashes remain unchanged; owned native scratch is absent. This local
      qualification is not GitLab execution. Peer admission, final hosted
      acceptance and formally distributed ETHOS proof remain open. Evidence:
      `build/verification/native-supply-gitlab-20261001/native-carrier-*`.
- [ ] 5.3 Bind macOS supervision to the native user Background domain; prove
      exact legacy GUI migration, unique registration, predecessor exit and
      successor identity. Observe registered services even without a carrier;
      conserve both domains, disabled overrides and unrelated plist bytes. Prior
      GUI-only native evidence does not qualify the new boundary. The actual
      review UID 510 has a reachable user Background domain and no GUI ASID; its
      exact GUI service probe returns unsupported, not service absence. Its
      LaunchAgents directory is absent. These read-only receipts establish the
      environmental root cause, not candidate acceptance. Eleven falsifying
      cases fail on the exact old implementation and pass after repair; 104
      supervision cases and 31 subtests also pass. The locked full source graph
      passes 1,811 tests per Python 3.12/3.13/3.14, with 97.83% statements and
      95.51% branches; all 1,219 tracked hashes remain unchanged during that
      run. Official OpenSpec and native format/type gates pass. Real macOS
      native qualification passes 49 cases and one Linux-only skip, including
      authentic published 4.0.4 installation, health, upgrade and rollback.
      Canonical listener and watchdog generations, both domain registrations,
      disabled overrides and plist hashes remain unchanged; isolated scratch is
      absent. Actual VM UID 510 then passes the existing native `release`
      session: 45 cases and one Linux-only skip, Background domain with no GUI
      ASID, all 1,219 source hashes unchanged and no net registrations,
      overrides or plist growth. Its native assets and eight producer records
      are individually hash-verified before the exact guest work root is
      removed; foreign build roots remain. The very same VM-built candidate
      archive also passes the authentic 4.0.4 upgrade/rollback case in its
      supported local GUI context, without rebuilding candidate bytes. Evidence:
      `build/verification/native-supply-gitlab-20261001/mac-domain-*`. Source
      `aede284e` is published to both existing proposal refs; GitHub PR 77 and
      GitLab MR 93 remain open. GitLab pipeline 9069 passes all seven
      Linux/Windows jobs; its macOS job passes 48 current cases but fails when
      the unchanged GUI-only 4.0.4 installer runs on the headless account.
      Peer-local admission of supported-context predecessor evidence, exact
      installed ETHOS proof and final hosted acceptance remain open; local proof
      is not relabeled as GitLab execution or a transferable Attestation. The
      acceptance criteria now separate an untouched published old payload's
      retained-runtime upgrade and rollback from recovery of unchanged state
      produced by the original old CLI. The earlier installer-only journey
      uninstalled the authentic payload before testing a route-modified fixture;
      its current-generated recovery input also could not prove old-producer
      compatibility. Those surrogate steps are removed. Both new native journeys
      and their complete peer matrices remain unqualified; the immutable old
      installer is not claimed to support headless execution. Stronger
      pre-fallback cleanup exposed a real recovery ordering defect: rollback
      deleted candidate and journal while submitted supervision remained.
      Recovery now requires exact native service removal and process-exit proof
      before fresh-candidate disposal, preserving unknown outcomes and prior
      supervision. Transaction and public-controller regressions pass; rebuilt
      native and complete-source acceptance remain required.
- [x] 5.4 Prove Linux systemd behavior on a real supported user service and in
      the declared container boundary, including explicit behavior when no user
      bus exists; remove session-only fallback processes.
- [x] 5.5 Prove current-user Windows Task Scheduler install, status, handoff,
      recovery, rollback, uninstall, command projection, and process-generation
      ownership from the native artifact.
- [ ] 5.6 Verify bounded teardown after success, assertion failure, exception,
      timeout, and interruption on every supported platform; compare exact owned
      services, processes, journals, payloads, commands, and temporary files
      before and after, preserving unrelated canonical installations. Replaced
      every unowned mkdtemp call in the current test inventory with pytest-owned
      temporary paths; the five affected modules previously left 76 directories
      after 120 passing tests and now leave zero. Native pytest retention is
      none/0, with a RED/GREEN configuration regression and zero retained runs
      after passing and assertion-failing focused suites. Platform
      service/process interruption proof remains separate and open.
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
      Removed tests/lifecycle/test_control.py and its stateless umbrella class;
      37 test bodies and all parameterization decorators remain unchanged across
      status, recovery, reload, rollback, uninstall and runtime loopback owners.
      The 1,028-effective-line carrier becomes files of at most 370 effective
      lines; shared listener evidence stays in the existing lifecycle fixture.
      The full five-module behavior selection retains 120 tests and 49 subtests;
      adding quality contracts yields 160 tests and 49 subtests. Broader test
      topology and structural enforcement remain under 6.2 and 7.5. SSE framing
      and recovery now have separate test owners; all 23 original methods and
      parameterization are preserved, and the former 541-effective-line carrier
      is removed. Fragmented-input regressions additionally verify prelude order
      and exactly-once downstream commitment. CLI contracts now separate
      dispatch and presentation from lifecycle observation, mutation and
      locking. The stateless class and its 1,002-effective-line carrier are
      removed; one CLI fixture owns output capture. All 38 test functions retain
      their normalized AST, assertions, parameters and decorators; the same 47
      tests and five subtests pass. The largest relocated carrier is 314
      effective lines. This reorganizes existing contracts without adding
      product behavior or changing native-service ownership. Evidence:
      `build/verification/4e3b897d4828f51cae722df6f6b6865d9cf775c1/cli-topology-*`.
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
      product-semantic checker that owns each concern. The single tracked
      responsibility map assigns all 1,212 carriers exactly once across 17
      roles, names one executable owner for each of 25 concerns, and maps all
      nine public surface classes to one invariant and implementation owner.
      Missing, overlapping, or incomplete declarations fail the existing `quick`
      and `governance` paths; no second quality registry was introduced.
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
      equivalents that add no unique semantic value. Locked Markdown lint now
      joins the existing governance graph. Three command and scope contracts
      reproduce the former skipped conformance and undeclared OpenSpec scope;
      those contracts, twenty real Markdown carrier cases, and two actual
      command-scope cases now pass. The normal governance entry runs the marked
      formatter and lint cases; all forty marked cases and 421 quality/Forge
      siblings pass. The complete matrix exposed a stale two-tool npm inventory
      contract, now reconciled without changing product dependencies. The frozen
      full graph passes 1,942 cases on each Python 3.12, 3.13, and 3.14 line
      with 97.26% coverage and all 1,221 source hashes conserved. Fifty online
      links pass. Native Vale now owns English spelling, repetition, canonical
      terms, and four concise phrases; nineteen real prose examples preserve
      code and link destinations. Ten original control-comment examples and two
      text-carrier omissions reproduce thirteen failures before repair. The
      existing native Markdown parser now rejects disabling comments, including
      inline, nested, and entity-encoded controls; twenty-eight native Node
      cases also preserve literal code, attributes, and explanatory comments.
      Native line, branch, and function coverage of that rule is 100%. The
      native HTML parser replaces raw comment matching after actual attribute
      false positives; no second Markdown or prose engine is introduced. Five
      new transitive packages are limited to that HTML parser; existing Markdown
      and entity libraries are promoted to explicit consumers. Registry
      signatures pass for 142 packages and 29 attestations. All 417
      quality/Forge sibling cases pass. The first full run passes 1,945 cases
      per Python 3.12/3.13/3.14, with 97.26% coverage and all 1,225 hashes
      conserved; 74 marked native cases run separately. Final review then
      exposes a natural Vale comment falsely rejected by a broad prefix; exact
      native control grammar replaces that prefix, and all 230 affected sibling
      cases pass. Final frozen full graph passes 1,945 cases per Python
      3.12/3.13/3.14 with five declared native-only skips, 97.26% coverage,
      seventy-five marked toolchain cases, and twenty-eight native Node cases.
      All 1,225 tracked hashes and 907 archived files remain unchanged;
      thirty-eight prose pages and fifty online links pass. Formal distributed
      ETHOS, mixed-language installed proof, native peers, and publication
      remain open. Evidence:
      `build/verification/native-python-binding-089f940d/`. Single-paragraph
      list spacing now uses the existing native Markdown rule API. Five
      separating RED cases pass after repair; all 44 native rule tests and 75
      marked quality siblings pass, with 100% rule coverage. Current formatting,
      38 Markdown pages, prose, links and official OpenSpec checks pass.
      Archived files remain unchanged; evidence is under
      `build/verification/a36a45c965b08a0ebff0650518f190641f906e5c/`.
- [ ] 7.5 Close structural measurement and enforcement together: verify
      file/function ELOC, logical statements, nesting and complexity semantics;
      classify the native-rule findings by product, tooling and test behavior;
      set risk-justified blocking limits, remove the observation-only acceptance
      contract, and simplify each affected semantic owner without suppressions
      or shallow extraction. Ruff C901 now enforces the native bound of 20
      across every Python role without exclusions. Stream commitment removes
      duplicate state and closure layers (24 to 20); responsibility declaration
      identity removes three parallel checks (22 to 16). The 15-bound preview
      identifies nine remaining candidates for semantic review, not nine
      automatic defects. Eight real-tool boundary cases prove native admission,
      and focused stream/responsibility/control contracts pass. ELOC, arguments,
      statements, nesting and remaining hotspots are still open. Evidence:
      `build/verification/4786f15de233c4957de37c1c7d8f37d9cb6ed471/`
      (`complexity-red.json`, `complexity-admission-red.log`,
      `complexity-admission-green.log`, `complexity-final-15-preview.json`,
      `complexity-focused.log`).
- [ ] 7.6 Enforce public API and repository-tool docstrings while excluding
      ornamental test docstrings; verify documentation signatures and
      implementation signatures cannot drift.
- [ ] 7.7 Make warnings fatal across tests, builds, docs, tools, native
      binaries, and CI; remove every known warning at its owner rather than
      filtering or baseline-suppressing it.
- [ ] 7.8 Verify commit subjects through one scoped Conventional Commit grammar
      in local hooks and both Forge paths, including generated lifecycle
      commits, with no duplicate parser or historical exception list. The native
      workspace commit policy now owns the existing exact subject grammar and
      mandatory SSH signing; the independent type/scope policy file and grammar
      compiler are removed. Repository quality consumes that same expression and
      checks HEAD when the integration base is equal instead of accepting an
      empty range. Both missing-policy and accepted-tip regressions fail before
      and pass after repair; 43 quality-contract tests pass. Event-scoped
      subject validation now receives exact base/head objects from the CUE-owned
      review, branch-push and tag projections. A regression with an invalid
      middle commit and a valid tip fails before and passes after repair even
      when integration refs already equal HEAD. Missing, malformed, unavailable,
      checkout-mismatched and non-ancestor event objects fail closed; tag checks
      select the tip and new-branch zero baselines cover reachable history.
      Focused quality/workflow contracts and actual POSIX event-variable
      projection pass. Hosted event-range execution and signature enforcement
      still require acceptance. Evidence:
      `build/verification/34ee6478d0726bb53fe5b30331213056b85c9da8/event-admission/`.
      Evidence:
      `build/verification/b98977f7b66bb69af81b3724933a09f3f4f8560c/commit-admission/`.
- [ ] 7.9 Run formatter, linter, type, architecture, dependency, security,
      documentation, configuration, and focused behavior gates on the migrated
      tree; require pristine output before the full suite. The unchanged
      `2d1fdccc` source passes every declared local component: governance,
      strict quality at Python 3.12, and Python 3.13/3.14 behavior. Each Python
      executes 1,948 tests with five native-asset skips and 118 declared
      deselections. Total branch-aware coverage is 97.27%. The single
      `mise run check` reached its 900-second deadline; only its unfinished
      Python 3.14 component was replayed and passed. This does not turn that
      timed-out invocation or installed ETHOS proof green. Owner-held evidence:
      `proxy-current-2d1-all-declared-source-components-20261002.json`.
- [ ] 7.10 Prove control effectiveness with isolated conformance cases for
      native tool settings, scope inclusion, nonzero exits, local entrypoints
      and hooks, and every CUE event route; a missing tool, skipped required
      check, empty scope or stale report must not establish acceptance.
      Complexity admission now executes the native checker for product, tools,
      tests and Nox paths; all over-bound examples were accepted before C901
      activation and are rejected afterward. The adoption profile now covers
      every repository carrier with the native `**` material scope, removing the
      incomplete 20-entry path list. A new policy regression fails before and
      passes after the change; all 41 quality-contract tests pass. The installed
      ETHOS scope evaluator previously classified five tracked supply-chain/root
      files as non-material; it now rejects them without an active Change and
      attributes all five to this Change when selected. Evidence:
      `build/verification/82af062fb23b42ea4e723131d2039f26ff1d04e6/material-scope/`.
      The two default proof descriptors now use ETHOS `verified-command` instead
      of unqualified subprocess mode; a focused RED/GREEN regression and the
      installed policy compiler confirm both verification providers are
      connected. `mise run quick` passes with 56 quality-contract tests. This
      fixes declaration wiring, not same-run Python evidence or final proof. A
      cold-context audit also reproduces dependent quality and matrix execution
      after failed governance. Nox now uses its native stop-on-first-error
      option; two falsifying prerequisite cases and the complete positive
      sequence pass. The same audit exposes OpenSSH's HOME-relative Unix-socket
      limit; the existing signing fixture now owns a short native socket and
      foreground agent with bounded cleanup, including deep-HOME cases. All 125
      sibling quality/Forge tests pass through the locked native environment.
      The exact final cold-context full graph passes 1,919 cases per Python
      3.12/3.13/3.14 with all 1,220 tracked hashes conserved. Complete local
      release tags, native project configuration, private environments and
      absence of operator credentials are verified. Other native-platform and
      formally distributed ETHOS proof obligations remain open. Evidence:
      `build/verification/native-supply-gitlab-20261001/native-harness-*` and
      `nox-prerequisite-*`. Other gate-path and event-scope audits remain open.
- [ ] 7.11 Reconcile the quality responsibility map with actual coverage,
      dependency, dead-code, security, documentation and delivery checks; close
      product/tooling/orchestration coverage independently, remove duplicate
      custom checkers, and leave unverified claims open. Exact source
      `cb55a8880ce66a4f0fbd755b9c6aae5ff27845d3` passes full quality with 1,604
      tests, 5 declared skips and 25 native/toolchain deselections. Product,
      tooling and Nox coverage pass independently; tools measure 3,164/3,231
      statements (97.93%) and 1,041/1,094 branches (95.16%), without reducing
      the 95% floors. Python 3.13 and 3.14 each pass the same 1,604 tests.
      Ownership, signing-context and artifact-manifest readers reject malformed
      schema identities; release construction, immutable publication, transport
      errors and governance failures now have executable contracts. Evidence:
      `build/verification/cb55a8880ce66a4f0fbd755b9c6aae5ff27845d3/quality.log`
      and `governance-python-matrix.log`. Governance also passes after native
      Prettier repaired the Forge-guide table; see
      `governance-format-repair.log`. These runs use offline link admission;
      external-link reachability is not claimed. The macOS native bundle at
      source `24d3f572bd9e703c798fdd34ea9ab0cb716386e0` also passes 36
      CLI/subprocess tests and 5 exact-host lifecycle tests (1 Linux-only skip);
      both raw logs are under that revision in `build/verification/`. The formal
      3.1.17 listener and sole formal LaunchAgent remain intact.
      Published-predecessor upgrade, successor publication, original-thread
      recovery, security and measured performance acceptance remain open.
- [x] 7.12 Eliminate current canonical OpenSpec INFO length findings by
      splitting oversized requirements at semantic boundaries without dropping
      obligations or scenarios; require official strict validation with no
      issues before exact-HEAD proof. All seven affected specs preserve every
      original requirement sentence and scenario exactly;
      `openspec validate --all --strict --json` reports 10/10 valid items and
      zero issues.

## 8. Development Environment and Supply Chain

- [x] 8.1 Define `mise` as the sole cross-platform developer entrypoint and
      provide minimal `bootstrap`, `check`, `native`, and `release` tasks that
      call existing ecosystem owners rather than shell wrappers.
- [ ] 8.2 Prove a clean Work Lane reconstructs independent `.venv`, `.nox`,
      `node_modules`, build, coverage, and temporary state from locks while
      sharing only content-addressed mise, uv, npm, and Python caches. An owned
      validation mirror reconstructs native environments and private package
      caches from exact source; empty-HOME bootstrap verifies 71 npm registry
      signatures and 22 attestations, and the complete graph passes 1,919 cases
      per supported Python. No source or lock hash changes, credentials, foreign
      environment, or integration authority are borrowed. This is a verification
      mirror, not an admitted Work Lane; cross-platform lane-native
      reconstruction remains open. Evidence:
      `build/verification/native-supply-gitlab-20261001/cold-native-development-*`
      and `native-harness-cold-*`.
- [ ] 8.3 Remove ambient interpreter, user-site, global mise configuration,
      system package, and another repository environment from local and hosted
      success paths; verify empty-HOME and empty-project-cache bootstrap. The
      native settings now disable legacy version files and version-host lookup.
      A missing-tool probe showed that `mise exec` could still run host Node
      even with `not_found_system_fallback = false`; one shared native
      `mise which` prerequisite now fails before any of the five repository
      tasks. An empty installed-tool probe rejects `quick` before it starts;
      locked bootstrap and quick pass with installed tools. Empty-HOME,
      empty-cache, and hosted qualification remain open.
- [x] 8.4 Online-audit every direct runtime, development, OpenSpec, Python,
      Node, mise, uv, Nox, packaging, documentation, CI Action, and release
      dependency; advance each to its latest compatible stable version in the
      existing SSOT. The 2026-09-30 official-source audit advanced uv to
      0.12.21, Cyclopts to 5.1.0, filelock to 4.0.7, three Python and three npm
      transitive packages, the GitLab Mise image to 2026.9.17, and both uv image
      digests. Other pins, including Node 26.10.0 and the GitHub Action SHAs,
      match current stable releases. The repository retains Python 3.12
      compatibility. The shared host's Homebrew Mise 2026.9.15 remains outside
      this project pin: the official formula has not yet advanced, so no
      parallel installer was added. A second current-source audit checks 299
      unique npm, PyPI, standalone-tool, and Action identities. It advances the
      now-published stable Mise 2026.9.18 and its verified multi-platform OCI
      index. Every direct dependency, Python package, and Action matches stable
      upstream; the npm resolver produces no Proxy lock change. Thirteen npm
      transitive identities remain behind upstream latest because the latest
      official parents constrain their versions. No unsupported major override
      or upstream fork is added; those constraints are disclosed, not called
      fully upgraded. A consumer audit then found unpinned hosted `gh` download
      commands. The existing Mise authority now pins the security-updated GitHub
      CLI 2.102.0; all three consuming job families install only that locked
      tool before acquisition and invoke it through Mise with prompting
      disabled. No Renovate dependency is introduced: this repository has no
      such consumer. The two native six-platform `gh` resolutions have identical
      lock SHA-256
      `510bc78ba64acfdf6c8a3e53d4e64cc0023b09f38a987b12829e0c8d1cd000e1`, with
      official artifact attestations and checksums. Locked macOS execution
      reports 2.102.0; 72 focused tests, repository-configured Ruff, formatting,
      Ty, and strict governance pass. The direct metadata was rechecked at
      `2026-09-30T15:46:14.731213+00:00`. This is the security release that
      fixes unsafe download traversal and attestation identity comparisons;
      hosted execution of the new locked CLI remains separate from source
      checks. The consumed package manager was also checked, not inferred from
      host PATH: locked Node initially selected bundled npm 11.19.1 while
      official stable is 12.1.0. The native Mise npm backend and precedence now
      bind the current npm without a wrapper or second package-manager owner.
      The language runtime remains Node 26.10.0; repository npm dependencies
      keep their unchanged official-parent contracts. npm's native AUBE package
      material is retained under `.mise/locks/`, bound by Mise's digest. Two
      resolutions preserve those exact bytes. One explicit Prettier ignore
      pattern defers only AUBE lock formatting to that native owner; repository
      JSON, other YAML, and text checks remain active. A RED/GREEN contract
      prevents formatter rewrites from invalidating the native digest. The
      frozen scoped checks pass 130 tests; platform execution and the final full
      source graph are verified separately. The first tracked-AUBE full run
      exposed an ignore-root mismatch and is not counted as passing. The native
      Prettier file-info test now verifies both the actual excluded AUBE carrier
      and an included authored YAML file. A cold exact-image Linux probe also
      found Node's missing `libatomic1`; the existing source job declares that
      runtime prerequisite before Mise. Both failures are repaired at their
      actual owners, not hidden by caches. A read-only exact-Mise-image Linux
      ARM64 probe passes with that native library prerequisite: Node 26.10.0
      selects the AUBE npm 12.1.0 executable, `npm ci` and all 71 signatures and
      22 attestations pass, and six input hashes remain unchanged. Its container
      and scratch are removed. macOS bootstrap passes independently; Windows
      execution remains unqualified. Evidence is retained by the coordinating
      AIGW owner under
      `build/verification/supply-chain-20260930/proxy-linux-npm12-libatomic.*`;
      this records a source-independent tool probe, not full Proxy lifecycle. A
      complete executable-consumer inventory leaves one actual Forge tool gap:
      GitLab observation and Runner admission call `glab`. It is now bound to
      stable 1.120.0 by the same Mise owner and required before tasks; the
      official GitLab release was rechecked on September 30. Native Git, SSH,
      supervision, archive, and platform-build commands keep their OS contracts.
      No unconsumed dependency updater or second installer is added. The npm
      closure is signed at `68cbbd4b`, after a passing five-session full graph:
      1,788 tests on each supported Python with five skips and 44 declared
      deselections. Native lock bytes, Mac and Linux package-manager precedence,
      and isolated cleanup pass; Windows hosted acceptance remains open. The
      later official stable Vale 3.24.0 now uses the same native Mise owner. All
      eight lock entries match official assets and digests; a second native
      resolution is byte-clean and other tool locks are unchanged. Three cases
      beside the rule pass native coverage, and a passing no-finding case is
      correctly rejected as uncovered. All 59 existing-scope English and
      Markdown contracts pass. This uses the existing governance test graph, not
      another prose pipeline. Complete native governance passes 76 toolchain
      contracts, and the full Python 3.12/3.13/3.14 graph passes 1,948 tests per
      interpreter with the same five release-only skips. Independent review
      finds no actionable defect. Installed shared quality and independent
      hosted tool-supply acceptance remain open. The official OpenSpec
      dependency is now stable 1.14.0. Native installation verifies 142 registry
      signatures and 29 attestations with no known vulnerability. Only the root
      and OpenSpec lock entries change; no transitive package is added or
      removed, and repeated resolution is byte-clean. Strict official validation
      passes all 10 items; the nine current specifications retain their exact
      129 requirements and 316 scenarios. The full five-session graph passes in
      329.819 seconds, with 1,948 passing tests per supported Python version and
      the same five release-only skips. Positive and malformed-scenario fixtures
      invoke the locked official CLI from their own working directory and assert
      the selected item identity; the earlier supplier-root fixture calls did
      not test those fixtures and are excluded. Source bytes are preserved by
      the completed check. Installed-product proof, peer platform execution, and
      final acceptance remain open.
- [x] 8.5 Regenerate `mise.lock`, `uv.lock`, and `package-lock.json`
      deterministically; verify a second resolution is byte-clean and no
      duplicate version literal controls behavior. Native Mise verified seven uv
      platform assets and attestations; uv resolved 50 packages; npm updated
      three compatible transitive entries. Second resolutions left all three
      locks unchanged. Bootstrap verified 71 npm signatures and 22 attestations
      with zero known vulnerabilities; quick passed 56 tests, the full
      five-session graph passed, official OpenSpec passed 10/10, and the native
      release asset passed 40 interface and handoff tests without touching the
      live service.
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
      admit and execute the exact-source Runner jobs. Related local contracts
      pass 166 focused tests. The final full graph passes governance and all
      three Python versions; each executes 1,784 tests with five skips and 43
      declared deselections. Statement and branch coverage remain 97.81% and
      95.49%, above the unchanged independent floors. The combined macOS native
      session passes 50 tests with one Linux-only skip, including the signed
      published 4.0.4 predecessor-to-candidate upgrade and rollback. Its
      isolated processes exit; canonical listener PID 2450 and watchdog remain
      unchanged. Evidence: `build/verification/native-ci-full-final.log`,
      `native-ci-lifecycle-final.log`, and `native-ci-gitlab-lint.json`; the
      official GitLab dry-run is valid with nine dev jobs and no warnings.
      Hosted platform execution and fleet admission remain open; Windows ARM64
      requires x64 Mise to select the locked x64 tool assets.
- [ ] 9.12 Qualify the paired native journeys in 5.3: untouched published
      predecessor payload through current-control upgrade and rollback, and
      unchanged old-CLI-produced recovery input through current public recovery.
      Prove complete payload identity, bounded old-controller process exit,
      public-operation cleanup before fallback teardown and host conservation.
      Recovery must admit selector, snapshot, command ownership, and exact
      native identity before disposal; failed Windows queries remain unknown.
      The frozen `2d1fdccc` review's GUI-only installer failure under headless
      UID 510 is historical failure evidence, not a continuing requirement to
      provision a GUI or a pass for the replacement criteria. Complete native
      macOS and Windows matrices remain required. Actual frozen `59909976`
      review pipeline 9261 reached Runner 118 and exposed `ERROR_PATH_NOT_FOUND`
      from the exact native scheduled-task query. The file-only absence mapping
      misclassified a fresh installation as degraded and cascaded into lifecycle
      and teardown failures. Extend the existing exact-query boundary for both
      documented not-found HRESULT values; preserve refusal of access, service,
      malformed XML, and timeout results. Distinguishing unsigned and signed
      path-not-found cases fail on the old implementation; the minimal
      exact-query repair passes all 41 Windows supervision source tests. A
      read-only native case records the actual task name, principal metadata,
      and HRESULT without provisioning an identity. Fresh native acceptance and
      current-user session applicability remain open; original pipeline failures
      are retained.
- [ ] 9.1 Define the complete CI graph in CUE—quality, Python matrix, native
      assets, platform lifecycle, release metadata, publication, and parity—with
      explicit facts proved by each job. GitHub review of signed `2c696d81`
      passed all declared native asset and predecessor compatibility jobs,
      including the 52-test Windows upgrade and rollback session. Its sole root
      failure was online link verification: all 95 timeouts targeted the
      declared intranet GitLab repository from a public runner. The existing
      link invocation and CUE caller now select one declared peer and exclude
      only the other exact repository's network checks. Native URL aliases,
      malformed declarations, and selected/public/local bad links retain
      refusal. All 72 focused cases and 295 affected tests pass; the complete
      source graph passes 2,032 tests on each Python line with unchanged
      coverage floors. The real GitHub-selected check has 149 valid links and 95
      explicit exclusions, not 95 accepted timeouts. Fresh hosted qualification
      and shared identity admission remain required. GitHub review of signed
      `c50b1e36` passed all applicable source, native, predecessor,
      branch-proof, and admission jobs. GitLab source governance also passed;
      its native release jobs stopped before compatibility because the broad
      verification module selected Node-dependent peer-link cases despite an
      intentional Python-only tool graph. Those exact cases now live with the
      existing governance test owner. All 296 affected tests and 11 native
      Python-only toolchain cases pass; every original case and floor remains.
      Qualify the affected hosted native jobs again without adding an unrelated
      runtime.
- [ ] 9.2 Generate GitHub Actions and GitLab CI from the CUE model, verify
      semantic parity and provider-specific deltas, and reject hand-edited
      projection drift. The Python-only branch proof and release-asset binding
      now select the official native Python shell at their existing CUE owner.
      The complete workflow file passes 45 native contracts; strengthened shell
      cases first failed on the old Bash selection. Missing or skipped jobs,
      unknown events, absent or ambiguous archives on either side, and quoted
      paths retain refusal or preservation. Stable actionlint 1.7.12 passes the
      actual projections in 0.19 seconds, with a real ShellCheck SC2086
      counterexample still rejected. The canonical full source check passes
      governance and all three Python versions: 1,948 tests pass per
      interpreter, with five native-asset cases reserved for the release
      session. Statement coverage is 97.84% and branch coverage is 95.45%.
      Independent code review found no actionable defect in the frozen six-file
      patch. Exact-HEAD proof, installed shared-contract acceptance, and hosted
      execution remain open.
- [ ] 9.3 Cover proposal creation and update, review SHA, maintainer
      fast-forward, `dev`, `main`, and tag events; verify every admissible
      integration path triggers the required exact-SHA evidence. Accepted source
      `a3ef6f7e` passes GitHub review 34989825588 and GitLab review 6779,
      including native Windows/macOS/Linux qualification and
      authentic-predecessor journeys. PR 45 and MR 63 merged without changing
      the reviewed object; both remote proposal refs are absent. Tests now
      distinguish POSIX permissions from portable persistence, parameterize
      declared release targets, and wait for actual traffic completion rather
      than another thread's readiness observation. ETHOS source acceptance
      permits the active delivery-inclusive Change without premature archive.
      Remaining path coverage and native required-status enforcement stay open.
- [ ] 9.4 Separate independent jobs for fast quality, Python 3.12/3.13/3.14
      compatibility, macOS, Linux, Windows, release construction, and
      publication; remove monolithic verification and meaningless duplicate
      runs. The dependency refresh at signed `f20c7e73` passes GitHub review run
      35006230962 and GitLab pipeline 6790, including Windows Python 3.12–3.14,
      three native assets, authentic predecessor compatibility on three
      platforms and Linux systemd lifecycle. A hosted cache-reservation warning
      exposed concurrent uv writers sharing a default key. One CUE setup
      definition now scopes that native cache by job and matrix index; the new
      regression fails before and passes after, and focused/static/governance
      checks pass. The cache correction still requires hosted observation;
      required-check enforcement and the remaining CI graph audit are not
      closed. Evidence:
      `build/verification/f20c7e73107f1b1aaacff7bdf7c2d8eb781d185b/`. The same
      unchanged signed object is now accepted locally and on both peers at
      main/dev: GitHub accepted runs 35007539791/35007537239 and GitLab
      6792/6791 all pass. Windows native logs record 41 passed with one
      platform-specific skip, and retained-predecessor compatibility records
      four passed. PR 46 and MR 64 are merged without object rewriting. The full
      graph revealed two obsolete interpreter-only cache assertions in the Forge
      fixture. They are removed in favor of the existing all-writer semantic
      cache regression; each platform still requires exactly one setup action.
      All 49 Forge/projection contracts and the full three-interpreter graph now
      pass. Signing authorization resumed through the original identity. The
      cache/stream repair and subsequent 4.0.1 release preparation are accepted
      at identical local and peer main/dev; both review proposals are merged and
      absent. Review, accepted-ref and tag pipelines pass. Hosted cache
      reservation recurrence and the remaining graph/admission audit remain
      distinct from this successful publication.
- [ ] 9.5 Define when exact-SHA evidence may be reused and when platform,
      environment, source, lock, or release changes require new execution;
      verify reuse cannot turn stale or partial proof green.
- [ ] 9.6 Require each selected Forge to execute the same macOS, Linux, and
      Windows functional proof semantics at the exact revision; qualify
      project-local runner admission before making the stricter graph required.
      Keep Windows ARM64 functional evidence distinct from native x86_64 ABI
      proof. The local GitLab projection separates Python-version nodes from
      OS-function nodes and MR-review from protected native runners, without a
      cross-trust CI cache. CUE, repository checks, and GitLab dry-run lint
      pass. The published `33a9e9ca` Linux API graph passes all seven jobs on
      protected Runner 114. Runner 35 is the current project-only Debian VM
      review executor, not a retired runner; protected and review admission
      remain separate. Signed source `33cadb7d` passes all eight GitLab review
      jobs in pipeline 9283 and all nineteen applicable GitHub jobs in
      run 37048210068. Windows Runner 118 passes twelve toolchain cases and
      fifty-two native lifecycle cases with one Linux-only skip; macOS Runner
      116 passes fifty-one native cases with two platform-specific skips. Linux
      review, Python, quality, performance, native assets, and the
      published-predecessor journeys pass in their declared contexts. Protected
      push and final installed-product qualification remain separate. Original
      API and trace evidence is retained in the owner-held final audit.
- [ ] 9.7 Verify GitHub and GitLab authentication, SSH agent, author identity,
      commit signature, tag signature, protected-branch, proposal-branch, and
      automatic merge behavior without password prompts or private-key mutation.
      Release 4.0.0 uses one verified product signing identity on both peers. A
      bounded main/dev linear-history exception admitted the already-reviewed
      signed merge object; both complete protection snapshots were restored
      exactly. Required-status admission remains an explicit governance gap;
      successful CI is not proof of enforced checks. A fresh accepted-source
      audit also finds seven owner-confirmed historical committer aliases for
      the same user. Correct them through ETHOS's exact committer-only history
      repair; preserve authors, other contributors, message bytes, timestamps,
      trees, and ordered parents. Current signing configuration does not prove
      that historical repair or peer attribution.
- [ ] 9.8 Ensure proposal branches are unprotected, merge automatically after
      required evidence for the maintainer policy, and are deleted on merge;
      verify no remote `work/*` or stale proposal remains.
- [x] 9.9 Run both generated CI projections for the exact candidate and verify
      `dev`, `main`, and the final tag receive the intended green graph with
      readable, bounded job output. At released commit `a3ef6f7e`, GitHub
      dev/main/tag runs 34991338911/34991338647/34991534162 and GitLab pipelines
      6780/6781/6782 pass. The tag graph produces signed assets for all three
      platforms and executes native Linux lifecycle acceptance. Exact results
      are retained in
      `build/verification/a3ef6f7e93ed491ecc6da653eeb5ba6ad59502e0/formal-ci.json`.

## 10. Release and Installed Product Proof

- [ ] 10.1 Determine the next version from actual public compatibility, update
      sole-owner `VERSION`, package metadata, Changelog, documentation, and
      asset naming, and verify strict SemVer and Keep a Changelog consistency.
      Published 4.0.0 is justified by commit `17750153` removing the public
      flat-installation migration path, not by internal package movement.
      Generation-based 3.1.17 upgrades remain verified. `VERSION`, local product
      tags, canonical Changelog sections, and release metadata now form one
      mechanically checked identity; 25 unpublished historical headings were
      folded into the tagged releases that actually carried their changes
      without dropping a user-visible entry.
- [ ] 10.1.1 Qualify current Changelog navigation and native peer locators after
      absorption of the signed product-owner source. Preserve every historical
      entry, verify neutral headings and both actual destinations, and keep
      SemVer, YANKED, current locks and three-platform CI responsibilities
      intact. Source checks, accepted integration and publication remain
      separate.
- [ ] 10.1.2 Qualify the accepted installed ETHOS identity/reference contract,
      reject reachable wrong-repository targets, and reconcile historical peer
      tag differences through its authorized repair contract. Verify each peer's
      actual result without a private map or duplicate checker.
- [ ] 10.2 Build reproducible macOS, Linux, and Windows native bundles from the
      locked candidate; verify contents, modes, manifests, checksums,
      signatures, SBOM, provenance, and common-platform byte identity where
      applicable.
- [x] 10.3 Verify release source is clean, signed, exact-HEAD proved and
      immutable, with current source-acceptance authority, before creating one
      signed annotated tag object. Delivery-inclusive Change obligations remain
      open until observed; archive is not a prerequisite for their release
      input. Commit `a3ef6f7e93ed491ecc6da653eeb5ba6ad59502e0` has passing full
      proof `eef7a08721efba8df50db1fe63feddbf8c0b3241114559491f89c182e09232bc`;
      tag `v4.0.0` identifies signed object
      `d185e9b83c9109673b6a4ba83ede93b9348c1573`.
- [x] 10.4 Project the same signed commit and tag objects to each selected Forge
      through independent exact-CAS operations; verify no author, committer,
      parent, tree, message, or signature rewriting. Local main/dev/candidate
      and both peers' main/dev equal `a3ef6f7e`; both peers expose exact tag
      object `d185e9b8`. The public parity verifier confirms the common tree and
      product trust anchor.
- [x] 10.5 Publish complete matching Release inventories on GitHub and GitLab;
      independently verify byte digests, signatures, trust anchors, metadata,
      and user-facing link identity from fresh persisted state, including
      idempotent and concurrent publication paths. Both published 4.0.0 Releases
      contain the same 8 signed files. The public publisher verifies downloaded
      bytes; the separate persisted-state verifier returns `verified=true`,
      `assets_equal=true`, and `tree_equal=true`. Publication regression
      contracts pass 105 tests and 24 subtests, including existing, partial and
      conflicting publication states. Evidence:
      `build/verification/a3ef6f7e93ed491ecc6da653eeb5ba6ad59502e0/formal-publication-verified.json`
      and `publication-contracts.xml` in the same directory.
- [x] 10.6 Upgrade the preserved working installation from the previous accepted
      release, prove runtime health and active-target no-op, roll back, recover,
      re-upgrade, uninstall, and reinstall using only published artifacts. The
      formal macOS bundle passes all 4 authentic 3.1.17 predecessor tests,
      including upgrade, rollback, re-upgrade and precise teardown. Production
      then upgraded to 4.0.0 through admission-preserving handoff, retained
      3.1.17 rollback, and proved active-target no-op; predecessor processes
      exited. All 37 protected configuration/trust/client files remained
      byte-identical. Canonical production was not deliberately uninstalled or
      rolled back for testing. The next formal 4.0.1 macOS bundle passes
      authentic published 4.0.0 upgrade, rollback, re-upgrade and exact
      teardown. Native production handoff then installs those signed,
      dual-peer-verified bytes, retires predecessor PID 6678, retains 4.0.0
      rollback and passes status, doctor and active-target no-op with all 37
      protected files unchanged. Evidence:
      `build/verification/c20b086e9095d0666ab194a886eb320434a265d3/`.
      Accepted-branch Windows run 35212800505 exposed a locked-module teardown
      defect; source inspection and a distinguishing regression proved that
      generation retirement omitted watchdog and prewarm roles. The existing
      exact-executable process owner now includes those roles without touching
      unrelated executables; both omitted-role cases fail before and pass after
      repair. Purge errors retain the native numeric OS code without leaking
      operating-system detail. Focused validation passes 175 tests with 116
      subtests and 74 disposal tests with five subtests. The signed repair
      commit `23e7de23bcd40e1ac5ab13ea59a6af0c046d2670` has exact-HEAD proof
      `ff86807b9f06c86ab7ebb3a28a5dff944c5ebb37cb03a488477ab9a26c177395`; local
      and both Forge `main` and `dev` refs identify that object, with GitHub
      main run 35308290739 and GitLab main pipeline 7379 passing. GitHub
      dispatch 35308330965 then downloads the published 4.0.3 and 4.0.2 assets
      and passes the same 49-test lifecycle suite on macOS, Linux, and Windows
      in jobs 105485011300, 105485011436, and 105485011460. The suite proves
      authentic predecessor install and health, traffic-preserving upgrade,
      active release health, recovery, rollback and no-op, re-upgrade, reload,
      purge uninstall, clean reinstall, exact teardown, and preservation of the
      canonical service. The production 4.0.3 installation remains running and
      accepting, reports 86 verified files, retains 4.0.2 rollback, has no
      transaction, and passes all six doctor checks.
- [x] 10.7 Verify installed status reports exact release, payload, manifest,
      service, process, listener, command projection, and transaction state
      without consulting source, Git, uv, Nox, ETHOS, or a Forge. The isolated
      4.0.0 acceptance remains recorded in
      `build/verification/a3ef6f7e93ed491ecc6da653eeb5ba6ad59502e0/production-isolated-status.json`
      and `production-doctor.json`. The current production observation reports
      4.0.3, 86 verified payload files, the owned command projection, a running
      accepting listener, admission-preserving handoff capabilities, finalized
      handoff state, no payload transaction, and retained 4.0.2 rollback; all
      six doctor checks pass.

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
      are clean. Native Markdown titles and prose wrapping replace private
      carrier exceptions. Semantic token comparison preserves pure reflow across
      thirty-one unchanged-content pages; native titles and five edited guidance
      or specification carriers are intentional changes. All 907 archived files
      retain their exact hashes. Complete native governance and the full local
      Python graph pass. Eight explicit English replacements preserve actors,
      obligations, conditions, and evidence limits. Native Vale and actual
      disabling-comment counterexamples now run through one governance entry;
      current-field semantics are not inferred from a green style check. Final
      current-source format, native prose, official OpenSpec, and full Python
      graph pass. Both native review planes pass at signed `33cadb7d`;
      accepted-runtime qualification and final closure remain open.
- [x] 11.4 Rename Decision Records to `dr-<sequence>-<subject>.md`, complete the
      decision register, and add only decisions that explain enduring product
      boundaries or rejected alternatives. All six current records have
      contiguous semantic names, required sections, and one register entry; the
      nine decision-contract tests pass.
- [ ] 11.5 Audit `.editorconfig`, `.gitattributes`, `.gitignore`, `.npmrc`,
      pytest, pyproject, mise, uv, OpenSpec, ETHOS adoption, release, and
      quality configuration; make each field reside in its true tool authority
      and delete stale or duplicate entries. Ignore rules now cover actual
      generated roots and optional code-intelligence projections, while authored
      `config.toml` stays visible. Obsolete flat packaging, worktree, and
      ETHOS-state exclusions are gone. Pytest and Coverage use native TOML;
      direct discovery, explicit `--rcfile`, three Python Nox sessions, and the
      macOS native asset passed locally. Git attributes keep text at LF under
      `core.autocrlf=true` without changing binary bytes; EditorConfig and Taplo
      agree on two-space TOML indentation. Contributor guidance now links the
      native workspace commit policy; coverage guidance uses the configured
      at-least comparison. Current JSON and JSONC configuration now joins the
      existing native formatter and text-byte scope; editor defaults use the
      same indentation. Native Markdown configuration is now one module, with
      its direct native tests and vocabulary included in the same tracked UTF-8,
      LF, final-newline, and trailing-whitespace policy. The removed YAML is not
      retained as a fallback. Native interpreter selection now has one Mise
      tool-aware environment owner. Direct proof, local tasks, and native CI
      synchronize the locked environment before execution, without
      executable-name ambiguity or no-sync false acceptance. Actual nested-path
      regressions cover missing and stale environments plus changed locks; the
      governance graph and each native platform execute them before dependent
      work. Native UTF-8 diagnostics now remain observable under a legacy
      ambient encoding. The same-source Windows job then exposed a different
      binding error: Mise supplied its Python installation directory, and uv
      repeatedly recreated a ready environment before failing to remove a locked
      directory. Mise's official resolver now supplies the executable; native
      conformance rejects a directory binding and proves configuration and
      owned-content preservation across consecutive consumers. Local focused
      tests pass. The same signed repair passes the complete Windows lifecycle
      and published-predecessor journey in GitLab job 47475, without a Runner
      rebuild, account replacement, or synchronization bypass. This is not a
      claim about a new ordinary-user logon. Actual tool-subset regressions now
      prove Python binding only when Python is selected; acquisition-only gh
      jobs do not require an absent interpreter. Both review CI planes pass; the
      remaining root-carrier audit and shared installed quality contract stay
      open. Stable npm 12.2.0 uses the native Mise backend and generated AUBE
      graph; the old repository sidecars retire through that producer. Native
      lock format 3 retains all 68 existing platform inputs and adds 11
      discovered entries; the minimum reader and actual host/CI Mise are
      2026.9.18. Actual pipeline 9025 disproved recursive workflow-variable tag
      expansion; Linux review and protected jobs now share one CUE body and use
      direct native scheduling variables with no intermediate alias. Windows
      native release selection uses the running interpreter ABI, not the host
      CPU, and native tests own short disposable roots independent of checkout
      depth. Pipeline 9030 proves direct Linux Runner assignment, source, Python
      matrix, and performance at signed a52f66c6. Its native Mac job rejects
      missing gui/510; its Windows job exposes deep service-account TEMP and
      inherited Nox TMPDIR. Native child temporary variables now share the same
      owned root; the Runner owner must provide a short isolated native TEMP
      input. Pipeline 9032 passes all Linux nodes and 49 Windows native checks,
      but one mocked-launch test unnecessarily prewarms a real bundle and leaves
      a locked module at cleanup. That invocation-only contract now runs in the
      non-native suite with a synthetic manifest and a bounded mock scope; its
      assertions remain intact. Fresh native suite acceptance remains required.
      The current candidate's GUI-only dependency is reopened in 5.3. The paired
      authentic payload and old-producer criteria in 5.3 replace the obsolete
      installer's GUI prerequisite; signatures, package acquisition or
      route-controlled traffic alone do not qualify either journey.
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
      touching user data or foreign state. Removed the exact 402 MiB ignored
      recovery checkout `build/tmp/.inline-image-hotfix-mrUh02` after proving a
      clean source, no open files, all 94 referenced objects, eight input blobs
      and 1,185 scratch-index entries retained in canonical Git history. Staged
      repair bytes and production listener PID 6678 remained unchanged. Broader
      residue inventory remains open. The current temporary-ownership reproducer
      and follow-up runs were removed from six exact stopped roots after
      open-file checks; raw failure/success evidence remains under the
      source-bound verification directory. Installed 4.0.1 and its canonical
      supervisor were not modified.
- [ ] 13.3 Merge or discard every local and remote proposal according to
      semantic value, delete merged proposal and remote `work/*` refs, retire
      obsolete Worktrees and leases, and verify only canonical repository-family
      members remain. Supply-chain PR 46 and MR 64 are merged; both remote
      proposal refs are absent. The current public absorbed-ref retirement
      command removed the exact stale local proposal at 40039cf7 after ancestry
      and ownership admission against accepted f20c7e73. Subsequent stream/cache
      PR 47/MR 65 and release-preparation PR 48/MR 66 are merged; both peer
      proposals are absent at their published source. Temporary-resource and
      complexity closures are accepted at signed 654b4734 on local and both peer
      main/dev; PR 49/50 and MR 67/68 are merged and both proposal refs are
      absent. GitHub review/main/dev runs 35043445407/35044336713/35044436255
      and GitLab 6814/6816/6815 pass. The active Work Lane remains required for
      unfinished Change obligations.
- [ ] 13.4 Remove failed unpublished tags, draft Releases, duplicate assets, and
      unreferenced records from both Forges and local storage while preserving
      formal immutable release history and required recovery evidence.
- [ ] 13.5 Freeze the complete candidate and run strict OpenSpec validation, all
      focused gates, full quality, Python matrix, three-platform native
      acceptance, reproducible build, security, performance, documentation, and
      repository-residue audits exactly once at final scope. Signed f4131ecd
      passes the full local quality graph; its exact-HEAD installed ETHOS proof
      does not pass. The python-quality command succeeds, but the native static
      provider rejects Python with
      `quality_static-analysis_python_native_evidence_unavailable`; the
      dependent python-matrix is not executed. Read-only inspection confirms
      that both installed and current ETHOS source reject NativeExecution with
      Python subjects before invoking their existing Python verifier. This
      product-owner defect is reported; unchanged proof retries and provider
      removal are not remedies. Required raw evidence remains under
      `build/verification/native-python-binding-089f940d/`. No peer publication,
      new ETHOS distribution, or final native acceptance is inferred. Completed
      local quality and matrix scratch is retired with source and evidence
      hashes conserved.
- [ ] 13.6 Complete every task from evidence, archive this Change through the
      current ETHOS public command, land the signed candidate, synchronize local
      `main/dev` and both Forge `main/dev`, and verify final tag CI and Releases
      are green and identical where required.
- [ ] 13.7 Prove the final installed product and clean repository family satisfy
      every modified capability, disclose any genuinely unverified external
      fact, and retain no active Change, Work Lane, proposal branch, temporary
      authority, or entity with no current consumer.
