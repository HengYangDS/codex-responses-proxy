## Why

The proxy's protocol core is useful, but the product is still exposed as a
Python source checkout: users invoke package modules, installation admits Git
source, release assets are source archives, and contributors depend on a
hand-written shell toolchain. Those choices leak implementation details into
UX and DX, preserve host coupling, and let partial delivery lanes substitute
for one terminal product.

## What Changes

- **BREAKING**: expose one self-contained `codex-responses-proxy` executable
  with `install`, `status`, `doctor`, `reload`, `uninstall`, and `version`;
  remove public Python/module/source-checkout entrypoints and aliases.
- **BREAKING**: bind installation, upgrade, rollback, supervision, and removal
  to verified executable, manifest, and owned-state identity rather than an
  installed Python interpreter or repository path.
- Make the secret-free provider manifest the only ordinary route registry.
  Adding a standard Responses provider changes one manifest table; a genuine
  wire difference may add one pure policy module referenced by that table.
- Preserve provider-portable replay and bounded recovery for `store=false`,
  provider item IDs, encrypted output, compaction controls, non-text agent
  content, empty responses, exact invalid-input failures, and HTTP 429 without
  reading or changing client conversation state.
- Remove proxy-owned ordinary-request concurrency admission. Codex owns its
  per-session concurrency, providers enforce their actual quotas, and the
  adapter retains only lifecycle drain admission, active-request accounting,
  one-call 429 relay, monotonic provider cooldown, and provider isolation.
- Replace PATH discovery and custom Python loops with a committed uv lock and
  small Nox session graph shared by contributors and both Forges. Test Python
  3.12, 3.13, and 3.14; require statement and branch coverage strictly above
  95 percent with clean successful output.
- Reorganize production code by semantic ownership and delete forwarding
  facades, obsolete package names, version-shaped symbols, duplicate lifecycle
  owners, and compatibility residue.
- Publish native platform assets on GitLab and GitHub with external actor,
  signing, trust, and remote inputs; verify required assets byte-for-byte.
- Freeze every existing worktree delta, absorb or supersede it, then remove all
  governed delivery lanes, leases, detached temporary checkouts, and old
  service residue after terminal acceptance.

## Capabilities

### New Capabilities

- `product-interface`: subject=public executable, repository-owned DX, and terminal lane state; reuse=new; change=add; facet:lifecycle=installation,operation,closeout; facet:surface=cli,release,docs,openspec; facet:authority=source,test,docs,openspec,claim,evidence.

### Modified Capabilities

- `provider-portable-responses`: subject=request-local portable replay, provider routing, and bounded recovery; reuse=extend; change=modify; facet:lifecycle=request,stream; facet:surface=protocol,provider,relay,test,openspec; facet:authority=source,test,openspec,claim,evidence.
- `runtime-upgrade`: subject=executable-bound installation, handoff, rollback, and supervision; reuse=extend; change=modify; facet:lifecycle=installation,recovery,operation; facet:surface=lifecycle,service,release,test,openspec; facet:authority=source,test,openspec,claim,evidence.
- `ci-diagnostics`: subject=locked verification, strict coverage, clean diagnostics, and native release acceptance; reuse=extend; change=modify; facet:lifecycle=validation,release; facet:surface=quality,ci,test,release,openspec; facet:authority=source,test,openspec,claim,evidence.

## Out of Scope

- Installing, configuring, verifying, or controlling AIGW, Codex, Claude Code,
  JetBrains products, Air, Junie, PyCharm MCP, ETHOS, or Workstation Control
  Plane.
- Editing Codex JSONL, SQLite, historical messages, item records, conversation
  metadata, or model metadata.
- General model routing, account management, credential storage, billing, load
  balancing, or provider quota policy.
- Preserving retired source paths, module entrypoints, compatibility aliases,
  provider-specific product names, or development-runtime dependencies.
- Treating local tests as hosted CI, Forge publication, installed-runtime, live
  provider, original-task, or housekeeping evidence.

## Impact

This changes the public command, runtime identity, service launch contract,
provider configuration, package ownership map, development environment, CI,
release assets, documentation, and repository-family closeout. AIGW remains an
independent client configuration control plane; JetBrains products, PyCharm
MCP, Codex history, Workstation Control Plane, and ETHOS remain outside the
installed proxy and are only external composition or acceptance surfaces.

## Lifecycle Boundary

This change closes the repository-source mutation and becomes archival before
governed landing. Hosted CI, identity projection, dual-Forge publication,
installed-runtime acceptance, live-provider checks, original-task continuity,
PyCharm MCP non-regression, and repository-family retirement remain mandatory
downstream obligations of claim `terminal-product-closeout-20260802`. Checked
task transfer statements bind those obligations to that claim; they do not
assert that the external states already exist.
