# Agent Entry Points

This repository is **Codex Responses Proxy**. It provides a local data-plane
compatibility adapter for third-party Responses endpoints; it is not the owner
of Codex conversation history or client configuration.

## Canonical Surfaces

- Project overview and setup: [README](README.md)
- Contribution and verification workflow: [CONTRIBUTING](CONTRIBUTING.md)
- Documentation root: [docs/README](docs/README.md)
- ETHOS adoption profile: [.ethos/profile.toml](.ethos/profile.toml)
- Active specification changes: [OpenSpec](openspec/)
- Authority and runtime boundary: [architecture](docs/architecture/authority-and-runtime-boundary.md)
- Change and release policy: [governance](docs/governance/release-and-change-policy.md)
- Decision records: [Decision register](docs/decisions/README.md)
- Durable boundary decision: [DR-0001](docs/decisions/dr-0001-control-plane-data-plane-boundary.md)
- Evidence policy: [evidence](docs/evidence/README.md)
- Independent forge operations: [operations](docs/operations/forge-operations.md)
- Release history: [CHANGELOG](CHANGELOG.md)

## Authority Order

1. Current user instruction and approved operational authorization.
2. Source code, tests, `VERSION`, and CI configuration.
3. Canonical documentation and durable decisions under `docs/`.
4. Generated runtime deployment under the platform data directory.
5. Logs, request captures, and host-local caches.

The installed runtime is a re-creatable post-release projection, never a source
of truth. Pre-release deployment is an invalid state.
Do not modify Codex session JSONL, SQLite state, archives, or model metadata to
repair a replay issue.

## Boundaries

- **Codex Desktop** owns per-conversation model selection and transcripts.
- **Client control planes** own provider configuration, credentials, endpoint
  selection, and client projection.
- **This proxy** owns local outbound Responses compatibility, its released
  payload and deployment, and native supervision.
- The proxy never reads or changes client configuration. Consumers use
  their own control plane to select one ordinary loopback HTTP endpoint.

## Required Verification

```bash
uv sync --locked --all-groups
uv run --locked --no-sync nox -s quick
uv run --locked --no-sync nox -s quality
uv run --locked --no-sync nox -s tests-3.12 tests-3.13 tests-3.14
uv run --locked --no-sync nox -s release
```

Use `codex-responses-proxy status --json` for read-only runtime evidence. Reload
and upgrade are transactional lifecycle mutations and must be communicated
before execution. Installation accepts only a fresh target or one verified
current native listener; an incompatible payload must be removed explicitly.

Released-source admission consumes one clean, signed release checkout and an
external trust anchor. It checks clean state on entry and before minting. The
final admission window binds `HEAD`, tag object, tag commit, tree, object format,
and immutable Git blobs; any worktree or identity drift is rejected. Dual-Forge
publication is verified independently and is not an installer dependency.

Uninstall must prove native-service absence and exact owned-process exit before
payload mutation. Process ownership requires the exact installed executable and
one declared private service role; identity is re-read before signalling and
boundedly rechecked afterwards. `--purge` trusts only a valid current payload
manifest, preserves unknown install content, and exits nonzero when residue
remains. On Linux without a user systemd bus or `crontab`, installation starts
no session-only fallback process.
