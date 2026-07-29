# Agent Entry Points

This repository is **Codex DMX Proxy**. It provides a local data-plane
compatibility adapter for third-party Responses endpoints; it is not the owner
of Codex conversation history or AIGW configuration.

## Canonical Surfaces

- Project overview and setup: [README](README.md)
- Contribution and verification workflow: [CONTRIBUTING](CONTRIBUTING.md)
- Documentation root: [docs/README](docs/README.md)
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
4. Generated runtime deployment under `~/.codex/dmx-proxy/`.
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
  payload and deployment, native supervision, and its reversible route adapter.
- A complete AIGW marked provider block is authoritative. Proxy install may
  place payload and service artifacts, but must not directly rewrite that route.
  An explicit compatibility bridge may delegate a requested endpoint change to
  AIGW's public CLI; it must never edit the AIGW config itself.

## Required Verification

```bash
python scripts/check_release_metadata.py --prepare-release
python scripts/check_markdown_presentation.py
python scripts/test_release_metadata.py
PYTHON=python3.12 RUFF=ruff TY=ty sh scripts/run-python-quality.sh
for py in python3.12 python3.13 python3.14; do
  "$py" -m compileall -q codex_dmx_proxy watchdog install.py uninstall.py control.py governance.py tests scripts
  "$py" scripts/run-python-tests.py
done
```

Use `control.py status --json` for read-only runtime evidence. A protocol-v2
reload is transactional but remains a lifecycle mutation and must be
communicated before it is performed. A legacy first migration may interrupt
traffic and requires its separate authorization. It binds a supported
historical manifest to its exact retired entrypoint and listener PID, then
replaces native supervision before successor proof; force skips only the quiet
wait, never integrity or identity checks.

Released-source admission requires a clean checkout before live publication
verification, then again on entry and before minting. The final admission
window binds `HEAD`, tag object, tag commit, tree, object format, and immutable
Git blobs; any worktree or identity drift is rejected.

Uninstall must prove native-service absence and exact owned-process exit before
payload mutation. Process ownership requires a Python executable whose exact
`argv[1]` resolves to the installed script; identity is re-read before signalling
and boundedly rechecked afterwards. `--purge` trusts only a valid current or
exact historical payload manifest, preserves unknown install content, and exits
nonzero when residue remains. Route restoration is a separate best-effort step,
so do not describe the whole uninstall sequence as atomic or fail-closed. On
Linux without a user systemd bus or `crontab`, installation starts no
session-only fallback process.
