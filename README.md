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

# Replace one drained, verified local listener; this briefly interrupts proxy traffic
python3 ~/.codex/dmx-proxy/control.py reload --json

# Stage a verified payload, then perform the same drain-protected replacement
python3 install.py --stage-only
python3 ~/.codex/dmx-proxy/control.py upgrade --stage <reported-stage> --json

# Apply a controller-only lifecycle fix without replacing an unchanged listener
python3 /path/to/source/control.py apply-control-plane --json

# Read-only payload and loaded-listener provenance evidence
python3 ~/.codex/dmx-proxy/governance.py --json

# Remove the service and restore a proxy-managed direct route
python3 uninstall.py

# Also remove the generated runtime payload
python3 uninstall.py --purge
```

`reload` and `upgrade` first wait for a five-second zero-active quiet window
**without closing admission**.

`apply-control-plane` is intentionally different: it is a source-side
controller repair, not a listener operation. Run it only from a committed,
fully verified source checkout. It first proves every listener, watchdog,
version, and support file is byte-identical to the verified live payload. It
then transactionally updates only `control.py` and the manifest, reports the
installed controller SHA-256, and leaves the verified listener and every active
Responses stream undisturbed. Any listener-payload change must use `reload` or
staged `upgrade` instead.

The listener rejects new `/v1/responses` requests with retryable HTTP 503 only
while drain is active, while already admitted requests finish. Only after the
same listener reports `draining=true` and `active_responses=0` may lifecycle
control make a replacement. A bounded drain lease reopens admission if a
controller crashes or disconnects; if the quiet window does not appear,
lifecycle control refuses without starting drain; an ordinary drain timeout
likewise changes no payload. The commands terminate only a verified listener,
require the watchdog to prove a new process ID when replacement is required,
and never touch Codex session files.

`governance.py --json` is read-only. It reports manifest integrity, route
authority, verified listener identity, and the loaded proxy source SHA-256 when
the loopback listener is reachable. It does not inspect or change AIGW settings,
Codex conversation state, credentials, or the proxy lifecycle.

### Reliability evidence

`status --json` also reports the listener's loopback-only, process-local
`runtime` snapshot when the verified service is reachable. It includes counters
for completed and incomplete streams, pre-content reconnects, bounded
`response_failed` recovery, encrypted-replay stripping, and classified upstream
outcomes. `last_failure` records only a stable class and Unix timestamp. It
never includes request bodies, tokens, credentials, headers, prompts, or
upstream error payloads. The endpoint is read-only and is available only at
`GET /healthz` on the loopback listener; it is not a remote monitoring API.
`runtime.draining` and `runtime.active_responses` together expose the lifecycle
barrier: while draining is true, no new Responses request may enter the active
set. `runtime.drain_lease_remaining_seconds` makes the fail-open lease visible.
The loopback-only `POST /control/drain` and `DELETE /control/drain`
endpoints are lifecycle internals used by `control.py`, not general APIs.

For a repeatable, privacy-bounded trend decision, use the source-side observer
with two or more comparable snapshots. It consumes the JSON that `status`
already emits; it neither contacts the listener nor changes its lifecycle:

```bash
python3 control.py status --json > /tmp/dmx-status.json
python3 scripts/observe-reliability.py \
  --status-file /tmp/dmx-status.json \
  --state /secure-local/dmx-reliability-baseline.json
```

The first snapshot establishes a baseline and returns `observe`, not an
inferred incident. A changed release, loaded-source digest, or listener restart
starts a new window. In a comparable window, local payload/listener faults and
new local stream failures are incidents; upstream `empty_response`, retryable
5xx, and `response_failed` are observations below three events and incidents
at three or more. New `proxy_draining` rejections are distinct from upstream
failures; when an operator has deliberately initiated maintenance, pass
`--allow-drain` to classify that delta as `observe`. The optional state file
contains only normalized counters, runtime identity, uptime, and observation
time. It never stores request bodies, responses, tokens, headers, prompts,
paths from the status payload, or upstream error payloads.

### One-time legacy bootstrap

The first upgrade from a listener released before the drain protocol has no
admission latch to invoke. In that narrow case, `upgrade` refuses by default.
Only an explicitly authorized `--allow-legacy-bootstrap` operation may proceed,
and it then requires the verified legacy listener to report zero active
Responses twice across a five-second quiet window before it changes any payload.
If a request arrives or the window does not complete, the upgrade refuses
without mutation. Once the replacement listener starts, all later reloads and
upgrades use the atomic drain barrier; the compatibility check is not a normal
operating mode.

If an urgent, separately authorized maintenance interruption is unavoidable,
`--force-legacy-bootstrap` may be combined with
`--allow-legacy-bootstrap`. It interrupts active Responses only after manifest
integrity and exactly one verified listener are proven; it is rejected for all
current drain-capable listeners and is not available to `reload`.

### Log retention and diagnostic safety

The proxy and watchdog write structured operational events only. They do not
persist request bodies, credentials, headers, prompts, query values, or raw
upstream payloads. Each log has a bounded rotating retention window; the default
is four 4 MiB proxy segments and three 512 KiB watchdog segments, including the
active segment. Oversized legacy segments are discarded without being copied or
read into evidence. Installation and payload refresh also remove the retired
`reject-*.json` raw request-capture files without reading or preserving them.
Native macOS service stdout and stderr are deliberately discarded so they cannot
become an unbounded second logging channel.

Set a durable retention policy at installation time:

```bash
python3 install.py \
  --proxy-log-max-bytes 4194304 \
  --proxy-log-backup-count 3 \
  --watchdog-log-max-bytes 524288 \
  --watchdog-log-backup-count 2
```

The selected bounds are rendered into the native user service. Updating an
installed service requires the normal installation or reload lifecycle and can
briefly interrupt proxy traffic.

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
| Upstream `response_failed` | `control.py status --json` | After the explicit 400, the proxy makes up to three strictly shrinking, pair-safe fallback attempts. If all are explicitly rejected, it may send one safely smaller dialogue-only attempt and then returns retryable 503 with `Retry-After: 3`; unrelated 400 responses remain unchanged. |
| DMX HTTP 477 `empty_response` | `control.py status --json` | Retry the unchanged request through the normal bounded transient-retry budget. On exhaustion, a streaming request receives a terminal SSE `error`; a non-streaming request receives standard HTTP 503 with `Retry-After`. Unrelated 477 responses remain unchanged. |
| SSE closes before completion | `control.py status --json` | The proxy retries only before sending substantive bytes downstream. If that bounded pre-content budget is exhausted, it returns retryable HTTP 503 with `Retry-After: 3` rather than an empty successful stream. |
| Need current reliability evidence | `control.py status --json` | Inspect the secret-free `runtime` snapshot; it proves listener-local counters, not recovery of a historical conversation. |
| Need a windowed incident decision | `scripts/observe-reliability.py --status-file <snapshot> --state <baseline>` | Compare only the same running payload; the tool is read-only and never reloads the listener. |
| Client ignores a route change | Client configuration lifecycle | A running client may need its normal reload; the proxy does not restart it. |

Logs are written under `~/.codex/log/`. They record bounded classifications,
request identifiers, and byte counts only; the proxy does not persist request
bodies, credentials, headers, prompts, query values, or raw upstream failures.

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
  "$py" -m compileall -q proxy watchdog platform_adapters install.py uninstall.py control.py governance.py tests scripts
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
