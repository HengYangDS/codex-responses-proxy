# Agent Entry Points

This repository is **Codex Responses Proxy**. It provides a local data-plane
compatibility adapter for third-party Responses endpoints; it is not the owner
of Codex conversation history or AIGW configuration.

## Canonical Surfaces

- Project overview and setup: [README](README.md)
- Contribution and verification workflow: [CONTRIBUTING](CONTRIBUTING.md)
- Documentation root: [docs/README](docs/README.md)
- ETHOS adoption profile: [.ethos/profile.toml](.ethos/profile.toml)
- Active specification changes: [OpenSpec](openspec/)
- Authority and runtime boundary: [architecture](docs/architecture/authority-and-runtime-boundary.md)
- Change and release policy: [governance](docs/governance/release-and-change-policy.md)
- Durable boundary decision: [ADR-0001](docs/decisions/0001-control-plane-data-plane-boundary.md)
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
- **AIGW** owns marked Codex provider configuration, credentials, endpoint
  selection, and cross-profile projection.
- **This proxy** owns local outbound Responses compatibility, its released
  payload and deployment, and native supervision.
- The proxy never reads or changes AIGW or client configuration. Consumers use
  their own control plane to select one ordinary loopback HTTP endpoint.

## Required Verification

```bash
python tools/release/metadata.py --prepare-release
python tools/quality/markdown.py
python tests/release/test_metadata.py
PYTHON=python3.12 sh tools/quality/run.sh
for py in python3.12 python3.13 python3.14; do
  "$py" tools/quality/tests.py --compile
done
```

Use `python3 -m codex_responses_proxy.commands.control status --json` for
read-only runtime evidence. A protocol-v2 reload is transactional but remains a lifecycle mutation and must be
communicated before it is performed. A legacy first migration may interrupt
traffic and requires its separate authorization. It binds a supported
historical manifest to its exact retired entrypoint and listener PID, then
replaces native supervision before successor proof; force skips only the quiet
wait, never integrity or identity checks.

Released-source admission consumes one clean, signed release checkout and an
external trust anchor. It checks clean state on entry and before minting. The
final admission window binds `HEAD`, tag object, tag commit, tree, object format,
and immutable Git blobs; any worktree or identity drift is rejected. Dual-Forge
publication is verified independently and is not an installer dependency.

Uninstall must prove native-service absence and exact owned-process exit before
payload mutation. Process ownership requires a Python executable whose exact
`argv[1]` resolves to the installed script; identity is re-read before signalling
and boundedly rechecked afterwards. `--purge` trusts only a valid current or
exact historical payload manifest, preserves unknown install content, and exits
nonzero when residue remains. On
Linux without a user systemd bus or `crontab`, installation starts no
session-only fallback process.
