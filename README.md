# Codex DMX Proxy

[![GitLab pipeline](http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-dmx-proxy/badges/main/pipeline.svg)](http://192.168.64.101:18086/dig/misc/tools/llm-third-party-api/codex-dmx-proxy/-/pipelines)
[![GitHub verification](https://github.com/HengYangDS/codex-dmx-proxy/actions/workflows/verify.yml/badge.svg)](https://github.com/HengYangDS/codex-dmx-proxy/actions/workflows/verify.yml)

| Project identity | Value |
| --- | --- |
| **GitLab Project Name** | `Codex DMX Proxy` |
| **GitLab repository path** | `codex-dmx-proxy` |
| **GitHub repository** | `HengYangDS/codex-dmx-proxy` |
| **License** | [MIT](LICENSE) |

Codex DMX Proxy is a local, loopback-only compatibility adapter for third-party
OpenAI Responses endpoints. It repairs replay incompatibilities at the network
edge without rewriting Codex conversations, SQLite state, JSONL archives, or
per-conversation model selection.

It is intentionally narrow:

- **Codex Desktop** owns conversations and the model selected for each one.
- **AIGW** owns provider configuration, credentials, endpoint selection, and
  projection to Codex profiles.
- **Codex DMX Proxy** owns outbound Responses compatibility and the lifecycle of
  its local listener only.

## When to use it

Use this adapter only when a verified third-party Responses endpoint rejects
replayed Codex state, for example:

- `encrypted content could not be verified`;
- `Missing required parameter: ... encrypted_content` from a legacy malformed
  replay block;
- a local image reference that the upstream endpoint cannot fetch;
- a transient `invalid_payload`, gateway timeout, or pre-content SSE interruption;
- a classified DMX HTTP 477 `empty_response` from its selected upstream;
- an explicit upstream `response_failed` execution rejection of replay context.

The adapter removes only deterministically incompatible outbound replay state.
For an explicit upstream `response_failed` rejection, it first makes up to three
strictly smaller fallbacks that each remove only the oldest contiguous,
tool-pair-safe input prefix, retain the latest user context, and drop the stale
`prompt_cache_key` from fallback requests only. If the upstream explicitly rejects
those pair-safe fallbacks as well, the proxy may make one final dialogue-only
request: the latest developer or system instruction before the active request,
where present, plus the latest user request, without assistant or tool replay. It
only sends that final request when it is safely smaller than the rejected replay.
Exhaustion is returned as retryable HTTP 503 with `Retry-After: 3`, so the client
may apply its own retry policy.
It preserves valid typed encrypted-content blocks, complete tool calls and outputs,
text, and remote image URLs whenever they remain in the pair-safe path. It is not a
general request transformer or a replacement for an upstream service with persistent
failures.

## Requirements

- Python 3.12 or later; the runtime uses only the Python standard library.
- A Codex installation that has already created `~/.codex/config.toml`.
- A verified third-party Responses endpoint. The adapter never stores an API key.

## Install

Clone a released source tag or download its GitLab release archive, then run:

```bash
python3 install.py
```

On Windows, use:

```powershell
py -3 install.py
```

The installer copies the executable payload to `~/.codex/dmx-proxy/`, registers
the watchdog using the platform's user-level service mechanism, and verifies
the loopback listener. It never downloads dependencies or collects credentials.

### AIGW-managed routes

When the active provider block is owned by AIGW, the installer deliberately
does not write `config.toml`. Register the already approved AIGW account once:

```bash
python3 ~/.codex/dmx-proxy/control.py adopt-aigw \
  --aigw-account dmx \
  --direct-url https://www.dmxapi.cn/v1
```

Thereafter, `enable` and `disable` ask AIGW's public CLI to update its canonical
endpoint and synchronize the marked projections. The proxy never edits AIGW's
configuration directly.

### Apply a route change

An already-running Codex client may cache configuration. Let the client reload
configuration through its normal lifecycle before expecting a changed route to
take effect. Do not create a new conversation or alter history merely to apply
a route change.

## Operate

```bash
# Read-only runtime evidence
python3 ~/.codex/dmx-proxy/control.py status --json

# Toggle a managed route without uninstalling the payload
python3 ~/.codex/dmx-proxy/control.py enable
python3 ~/.codex/dmx-proxy/control.py disable

# Replace one verified local listener; this briefly interrupts proxy traffic
python3 ~/.codex/dmx-proxy/control.py reload --json

# Remove the service and restore a proxy-managed direct route
python3 uninstall.py

# Also remove the generated runtime payload
python3 uninstall.py --purge
```

`reload` validates the installed payload, terminates only the verified listener,
and requires the watchdog to prove replacement with a new process ID. It never
touches Codex session files.

### Reliability evidence

`status --json` also reports the listener's loopback-only, process-local
`runtime` snapshot when the verified service is reachable. It includes counters
for completed and incomplete streams, pre-content reconnects, bounded
`response_failed` recovery, encrypted-replay stripping, and classified upstream
outcomes. `last_failure` records only a stable class and Unix timestamp. It
never includes request bodies, tokens, credentials, headers, prompts, or
upstream error payloads. The endpoint is read-only and is available only at
`GET /healthz` on the loopback listener; it is not a remote monitoring API.

## Design

```text
Codex -> 127.0.0.1:8791 -> verified Responses endpoint
           |
           +-- watchdog supervised by the native user service
```

The proxy forwards method, path, headers, and credentials unchanged. For
`POST /responses`, it may remove stale top-level reasoning replay items,
unreplayable local images, malformed legacy encrypted-content shells, and
`reasoning.encrypted_content` from `include`. It fails open: if a body cannot
be parsed safely, it forwards the original bytes unchanged.

Bounded retries apply only to explicitly classified upstream conditions. An
ordinary client-side 400, an encrypted-content validation error, and unknown
rejections are returned unchanged.

## Diagnose

| Symptom | First check | Boundary |
| --- | --- | --- |
| Encrypted replay error | `control.py status --json` | Confirm a healthy listener and enabled route before investigating history. |
| Upstream `response_failed` | Proxy log and request ID | After the explicit 400, the proxy makes up to three strictly shrinking, pair-safe fallback attempts. If all are explicitly rejected, it may send one safely smaller dialogue-only attempt and then returns retryable 503 with `Retry-After: 3`; unrelated 400 responses remain unchanged. |
| DMX HTTP 477 `empty_response` | Proxy log and request ID | Retry the unchanged request through the normal bounded transient-retry budget. If that exact condition exhausts the budget, return standard HTTP 503 with `Retry-After`; unrelated 477 responses remain unchanged. |
| SSE closes before completion | Proxy log | The proxy retries only before sending substantive bytes downstream. |
| Need current reliability evidence | `control.py status --json` | Inspect the secret-free `runtime` snapshot; it proves listener-local counters, not recovery of a historical conversation. |
| Client ignores a route change | Client configuration lifecycle | A running client may need its normal reload; the proxy does not restart it. |

Logs are written under `~/.codex/log/`. They record bounded classifications,
request identifiers, and byte counts only; the proxy does not persist request
bodies, credentials, headers, prompts, or raw upstream failures.

## Configure

The generated service supplies safe defaults. Use install arguments rather than
editing a generated service definition:

```bash
python3 install.py --port 8801 --upstream https://your.responses.endpoint
```

See [`config.example`](config.example) for the supported environment variables.

## Verify a source checkout

```bash
python3 scripts/check_release_metadata.py
python3 scripts/check_markdown_presentation.py
python3 scripts/test_release_metadata.py
for py in python3.12 python3.13 python3.14; do
  "$py" -m compileall -q proxy watchdog platform_adapters install.py uninstall.py control.py tests scripts
  "$py" tests/test_package.py
done
```

## Documentation

- [Contributor workflow](CONTRIBUTING.md)
- [Agent entry points](AGENTS.md)
- [Documentation map](docs/README.md)
- [Authority and runtime boundary](docs/architecture/authority-and-runtime-boundary.md)
- [Release and change policy](docs/governance/release-and-change-policy.md)
- [Decision record](docs/decisions/0001-control-plane-data-plane-boundary.md)
- [Evidence policy](docs/evidence/README.md)
- [Independent forge operations](docs/operations/forge-operations.md)
- [Read-only parity audit](docs/operations/forge-operations.md#parity-audit)
- [Release history](CHANGELOG.md)
