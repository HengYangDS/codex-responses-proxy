## Context

See [proposal.md](proposal.md) for motivation. The current tree already has a
provider-portable Responses kernel, cross-platform user supervision, signed
source admission, dual-Forge verification, and broad regression coverage. Its
remaining fault is architectural: source layout, installed layout, contributor
tooling, and release layout are treated as one thing. Existing worktrees also
contain overlapping partial solutions, so file-by-file iteration creates
multiple active truths.

The live 2.0.4 runtime must remain available until a verified successor is
ready. The repair must not read or mutate Codex JSONL, SQLite, conversation
history, item records, or model metadata. AIGW, ETHOS, Workstation Control
Plane, and JetBrains runtimes are independent external systems.

## Goals / Non-Goals

**Goals:**

- one public executable and one bounded command grammar;
- one declarative provider registry and one optional pure wire-policy seam;
- semantic packages whose physical dependency graph follows truth ownership;
- one locked repository environment and one small verification graph;
- native release assets, external trust inputs, and transactional deployment;
- one frozen candidate, one final proof cycle, and zero delivery-lane residue.

**Non-Goals:**

- general model routing, load balancing, budgets, billing, or cluster gateway;
- client account, credential, storage-policy, or endpoint management;
- JetBrains/Air/Junie/PyCharm configuration or MCP ownership;
- compatibility aliases for retired commands, paths, packages, or releases;
- cross-platform claims inferred from compilation on another operating system.

## Decisions

### 1. Release a native executable, not a Python application contract

PyInstaller builds one console executable on each native CI operating system.
It is chosen over zipapps, PEX, and ordinary wheels because those still require
a target Python runtime; over a rewrite in another language because the current
protocol code and tests are already valuable and the rewrite would add risk
without changing the contract. Python remains an implementation language and a
developer matrix, not a user dependency.

The executable embeds the provider manifest and default schema. Runtime-owned
state lives in platform-native data, config, and state directories. Service
managers execute the installed binary with a private service mode; public help
never exposes that mode.

### 2. Use one composition root and six public commands

`codex_responses_proxy/cli` owns argument grammar, result rendering, and
dependency assembly only. `install`, `status`, `doctor`, `reload`, `uninstall`,
and `version` call lifecycle or service owners directly; there are no command
facades mirroring modules. Errors are classified once at the CLI boundary:
human output is concise, JSON output is stable, and expected failures contain
no traceback or warning.

### 3. Make semantic ownership physically isomorphic

The terminal production packages are:

```text
cli/         command grammar and composition
protocol/    request replay, pairing, response projection, recovery grammar
providers/   manifest validation, route registry, pure wire policies
relay/       HTTP exchange, streaming, retry budgets, cooldowns
service/     listener, health, logs, and private service mode
lifecycle/   installed state, transactions, native supervision, migration
```

The dependency direction is `cli -> lifecycle/service`, `service -> relay`,
`relay -> protocol/providers`, and `lifecycle -> service`. Lower packages do
not import higher ones. Repository-only release, Forge, evidence, and quality
code remains under `tools/` and is not embedded unless it owns executable
runtime behavior.

Existing behavior is moved, not wrapped. Old `commands`, `deployment`,
`listener`, `payload`, `recovery`, `replay`, `runtime`, `supervision`, and
`transport` paths disappear when their owners move. Declaration-only
`__init__.py` files stay empty except for their package docstring.

### 4. Keep provider extension declarative and closed

One validated TOML manifest maps a provider slug to an HTTPS Responses base and
an optional policy name. A standard provider adds one table. A special policy
is a pure module selected by the manifest and may only transform or classify
wire data. It cannot perform HTTP, retry, credential, filesystem, lifecycle, or
client operations. The relay depends on the policy protocol, never a provider
name. A synthetic-provider test proves the extension radius.

`store=false` and provider-ID removal are protocol rules applied to each
request. They are not read from AIGW or any account configuration. Unknown
history remains fail-closed; official current controls such as
`compaction_trigger` and supported non-text agent structures receive explicit
portable projections.

Provider-route serialization is not a sound proxy invariant. A prior UCloud
new-account rate-limit incident justified temporary same-route single-flight,
but that service policy is not a durable provider contract. The installed
single-flight runtime also produced a two-minute local queue behind one long
stream. The terminal proxy therefore leaves per-session fan-out to Codex and
actual quotas to each provider. It owns no ordinary-request concurrency ceiling
or queue; active-request accounting remains only for transactional drain and
observation. The first real upstream 429 is still relayed after exactly one
call, establishes a monotonic provider-scoped cooldown, and blocks later
requests only while that observed instruction remains active.

### 5. Use uv for locking and Nox for orchestration

`pyproject.toml` holds concise project metadata, direct development groups, and
tool-native policy. `uv.lock` is the transitive dependency SSOT.
`.python-versions` is the supported interpreter list. Nox uses uv-backed
environments and owns only session composition. This separates dependency
resolution from orchestration without inventing another runner.

The public contributor surface is `uv run --locked nox -s quick`, `full`, and
`release`. CI selects its native interpreter/platform but calls the same
sessions. Custom shell environment creation, PATH tool discovery,
requirements files, and duplicated interpreter loops are deleted.

### 6. Build platform assets natively and compare the common contract

Each native Forge job produces an archive containing the executable, provider
manifest, license, and release manifest for its OS/architecture. `SHA256SUMS`
and a machine-readable asset manifest bind the set. GitLab and GitHub use
independent verified identities and tags but must publish byte-identical assets
for the same platform build. Actor emails, signer fingerprints, keys, trust
anchors, remotes, and API coordinates remain execution inputs, never source
defaults.

### 7. Replace the current runtime by one explicit predecessor migration

The terminal release recognizes only the immediately preceding supported
installed schema. Version and inventory are release data, not Python symbol
names. The new executable verifies the previous manifest and process identity,
stages the new owned state, starts a non-accepting successor, proves release,
manifest, endpoint, and health identity, commits ownership, then retires the
old service. Failure restores the verified predecessor. There is no general
historical compatibility framework.

### 8. Treat every existing lane as closeout input, not another writer

Before deletion, record each worktree's exact head plus staged, unstaged, and
untracked digests. Classify its content as absorbed, already represented,
superseded by this design, or externally blocked. Required behavior is
reimplemented test-first in the single terminal lane; pre-rename patches are
not overlaid. Governance closeout checks run only after the released runtime is
accepted.

## Risks / Trade-offs

- **Native binaries differ across platforms** -> build and smoke each platform
  natively; compare equivalent platform assets across Forges, not unlike OS
  binaries.
- **PyInstaller hidden imports or data omissions** -> derive embedded modules
  and data from the validated provider registry and run black-box help,
  version, status, manifest, and listener tests with Python removed from PATH.
- **Large package moves obscure protocol regressions** -> preserve behavior
  through tests first, use mechanical moves in batches, and run focused suites
  before the single final full gate.
- **Breaking lifecycle migration interrupts the active proxy** -> keep 2.0.4
  live until signed assets exist, use the transactional predecessor path, and
  retain rollback evidence until same-thread acceptance succeeds.
- **Nox becomes ceremonial duplication** -> limit it to three composition
  sessions; commands and policy remain in their semantic tools, not copied into
  Nox.
- **More configuration surfaces reintroduce hardcoding** -> manifest, runtime
  paths, release context, and actor identity each have one owner and machine
  scans reject personal, private-infrastructure, provider-branch, and local-path
  literals outside their legitimate boundary.
- **A provider later restores account protection** -> do not guess or encode an
  unpublished quota. The existing one-call 429 relay and provider cooldown
  react to the provider's current response without permanently reducing healthy
  accounts to one in-flight request.

## Migration Plan

1. Preserve the full current candidate and every lane delta by digest.
2. Add failing black-box CLI, native-build, provider-extension, architecture,
   and locked-environment contracts.
3. Move protocol/provider/relay behavior, then service/lifecycle behavior, then
   replace the public entrypoint and delete retired paths.
4. Freeze the complete candidate; run focused checks, one final full matrix,
   and one exact-HEAD ETHOS proof.
5. Land and publish the next release on both Forges with native assets and
   cross-Forge verification.
6. Install transactionally, prove all providers and the original Codex task,
   then verify the parallel PyCharm MCP surface read-only.
7. Close all governed lanes, detached checkouts, leases, temporary artifacts,
   and obsolete services; retain only immutable release and closeout evidence.

Rollback remains the exact verified predecessor until the successor has passed
runtime and same-task acceptance. After acceptance, no compatibility path is
retained in active code; history remains in Git and release evidence.
