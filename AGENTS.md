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
- Release history: [CHANGELOG](CHANGELOG.md)

## Authority Order

1. Current user instruction and approved operational authorization.
2. Source code, tests, `VERSION`, and CI configuration.
3. Canonical documentation and durable decisions under `docs/`.
4. Generated runtime deployment under `~/.codex/dmx-proxy/`.
5. Logs, request captures, and host-local caches.

The installed runtime is a re-creatable projection, never a source of truth.
Do not modify Codex session JSONL, SQLite state, archives, or model metadata to
repair a replay issue.

## Boundaries

- **Codex Desktop** owns per-conversation model selection and transcripts.
- **AIGW** owns marked Codex provider configuration, credentials, endpoint
  selection, and cross-profile projection.
- **This proxy** owns local outbound Responses compatibility and its own
  process lifecycle only.
- A complete AIGW marked provider block is authoritative. Proxy install may
  place payload and service artifacts, but must not directly rewrite that route. An explicit
compatibility bridge may delegate a requested endpoint change to AIGW's public CLI; it
must never edit the AIGW config itself.

## Required Verification

```bash
python scripts/check_release_metadata.py
python scripts/check_markdown_presentation.py
python scripts/test_release_metadata.py
for py in python3.12 python3.13 python3.14; do
  "$py" -m compileall -q proxy watchdog platform_adapters install.py uninstall.py control.py tests scripts
  "$py" tests/test_package.py
done
```

Use `control.py status --json` for read-only runtime evidence. A reload is a
service interruption and must be communicated before it is performed.
