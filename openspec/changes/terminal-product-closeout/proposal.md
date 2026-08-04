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

- `product-interface`: stable executable UX, repository-owned DX, native
  distribution, public lifecycle grammar, and terminal lane state.

### Modified Capabilities

- `provider-portable-responses`: manifest-only ordinary provider extension and
  complete request-local replay/recovery semantics.
- `runtime-upgrade`: executable- and manifest-bound transactional lifecycle
  independent of source checkout and Python installation.
- `ci-diagnostics`: one locked Nox projection with pristine success output,
  supported-Python coverage, and native executable acceptance.

## Impact

This changes the public command, runtime identity, service launch contract,
provider configuration, package ownership map, development environment, CI,
release assets, documentation, and repository-family closeout. AIGW remains an
independent client configuration control plane; JetBrains products, PyCharm
MCP, Codex history, Workstation Control Plane, and ETHOS remain outside the
installed proxy and are only external composition or acceptance surfaces.
