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
- **Codex DMX Proxy** owns outbound Responses compatibility, its released
  payload and deployment, native supervision, and its reversible route adapter.

## When to use it

Use this adapter only when a verified third-party Responses endpoint rejects
replayed Codex state, for example:

- `encrypted content could not be verified`;
- `Missing required parameter: ... encrypted_content` from a legacy malformed
  replay block;
- a local image reference that the upstream endpoint cannot fetch;
- a transient `invalid_payload`, gateway timeout, or pre-content SSE interruption;
- a classified DMX HTTP 477 `empty_response` (one precise,
  semantic-preserving recovery);
- an explicit upstream `response_failed` execution rejection of replay context;
- the exact observed `Invalid 'input'` union validation contract.

The adapter removes only deterministically incompatible outbound replay state.
For an explicit upstream `response_failed` rejection, it first makes up to three
strictly smaller fallbacks that each remove only the oldest contiguous,
tool-pair-safe input prefix, retain the latest user context, and drop the stale
`prompt_cache_key` from fallback requests only. If the upstream explicitly rejects
those pair-safe fallbacks as well, the proxy may make one final dialogue-only
request: the latest developer or system instruction before the active request,
where present, plus the latest user request, without assistant or tool replay. It
only sends that final request when it is safely smaller than the rejected replay.
Exhaustion, loops, or unsafe failures are returned as standard retryable HTTP
503 with `Retry-After: 3`, so the client may apply its own retry policy.
It preserves valid typed encrypted-content blocks, complete tool calls and outputs,
text, and remote image URLs whenever they remain in the pair-safe path. It is not a
general request transformer or a replacement for an upstream service with persistent
failures.

When the upstream returns the complete observed HTTP 400 `validation_error`
stating that `input` matched no expected variant, the proxy records one bounded
content-free structural diagnostic and may send exactly one smaller request.
That request retains only the latest system, developer, and user messages in
their original order, preserves top-level instructions, and removes stale
response, conversation, cache, and encrypted-reasoning bindings. Failure of
that request is terminal for this proxy operation: it cannot enter HTTP 477,
`response_failed`, transport retry, or SSE reconnect policies.
The structural diagnostic uses closed labels, bucketed cardinalities, presence
flags, and a capped categorical hash. Separate recovery events retain exact
byte lengths and retained/dropped item counts for bounded operational evidence;
neither surface records message values or unknown names.

## Requirements

- Python 3.12 or later; the runtime uses only the Python standard library.
- Git and OpenSSH, including `ssh-keygen`, for source and signature verification.
- A Codex installation that has already created `~/.codex/config.toml`.
- A verified third-party Responses endpoint. The adapter never stores an API key.
- Authenticated network access to both configured Forge APIs and Git remotes.
- The repository-tracked GitLab and GitHub signer policies, plus an independent
  absolute release trust-anchor file stored outside this checkout.

## Install

Installation is a post-release operation. Start from the exact clean checkout
whose `HEAD` is the signed annotated `v<VERSION>` tag. The installer requires
that clean state before live publication verification, checks it again on
released-source admission, and repeats the check before minting the payload
capability. Before invoking it, you may run the evidence-only command against
both independent Forge planes and retain its JSON result for audit:

```bash
python3 scripts/verify-publication-proof.py \
  --tag "v$(cat VERSION)" \
  --gitlab-remote "$GITLAB_REMOTE" \
  --gitlab-api-base "$GITLAB_API_BASE" \
  --gitlab-repo "$GITLAB_REPOSITORY" \
  --github-remote "$GITHUB_REMOTE" \
  --github-repo HengYangDS/codex-dmx-proxy \
  --gitlab-anchor packaging/release/gitlab-allowed-signers \
  --github-anchor packaging/release/github-allowed-signers \
  --json > /secure-local/codex-dmx-publication-proof.json
```

The verifier fails closed unless both provider-native signed tags, required CI
jobs, and formal Release records bind to the same source tree. The two committed
allowed-signers files are provider-specific publication policy. They do not
replace the installer's independent release trust anchor, which must be an
absolute regular file outside the checkout. JSON is evidence only and cannot
authorize installation. The installer performs the same live verification
in-process before it mints a one-use capability. Install the verified release
with the complete verifier inputs:

```bash
python3 install.py \
  --tag "v$(cat VERSION)" \
  --gitlab-remote "$GITLAB_REMOTE" \
  --gitlab-api-base "$GITLAB_API_BASE" \
  --gitlab-repo "$GITLAB_REPOSITORY" \
  --github-remote "$GITHUB_REMOTE" \
  --github-repo HengYangDS/codex-dmx-proxy \
  --gitlab-anchor packaging/release/gitlab-allowed-signers \
  --github-anchor packaging/release/github-allowed-signers \
  --trust-anchor "$DMX_RELEASE_TRUST_ANCHOR"
```

On Windows, replace `python3` with `py -3`.

The installer does not copy arbitrary working-tree files or accept a filesystem
stage. Admission reads immutable blobs from the signed tag, freezes `HEAD`, tag
object, tag commit, tree, and Git object format, then compares that complete
identity before and after its final clean-check. Worktree or identity drift
therefore prevents capability minting. The opaque one-use capability carries
the verified blobs, canonical receipt, and sidecar into a private sibling
transaction, which finalizes only after the listener proves the release,
aggregate serving-payload digest, receipt digest, manifest digest, and accepting
state. Failure restores the exact prior owned projection; an unprovable
committed handoff is retained as an explicit recovery-required transaction. The
installer never downloads Python dependencies or collects credentials.

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

# Hand off one verified protocol-v2 listener without closing its socket
python3 ~/.codex/dmx-proxy/control.py reload --json

# Read-only payload and loaded-listener provenance evidence
python3 ~/.codex/dmx-proxy/governance.py --json

# Remove the service and restore the exact adopted managed route
python3 uninstall.py

# Also remove the generated runtime payload
python3 uninstall.py --purge
```

Uninstall first attempts the recorded route restoration unless `--keep-config`
is selected. That step preserves drifted or unverifiable configuration and is
not an all-or-nothing transaction with later cleanup. Before any payload
mutation, native service removal must report `absent`, and every watchdog and
listener selected for termination must be an exact Python process whose
`argv[1]` resolves to this installation's script. Identity is re-read
immediately before signalling and boundedly rechecked afterwards; PID reuse
never authorizes signalling the new occupant. `--purge` then removes only files
owned by a valid current manifest or an exact supported historical inventory.
Unknown install content is preserved and reported with a nonzero exit rather
than a successful `Done` message.

For a protocol-v2 listener, installed-control `reload` is deliberately limited
to the same installed payload. It verifies the manifest and receipt, prepares a
non-accepting child, stops the old accept loop before `COMMIT`, and requires the
child to prove PID, transaction, release, aggregate serving-payload digest,
receipt digest, and manifest digest before `FINALIZE`. The listening socket
remains open throughout. Already accepted handlers drain to zero or a bounded
lease; a pre-finalize failure resumes the old process only after the child is
confirmed exited. An unconfirmed abort fails closed rather than risking two
accepting processes.

Changing payload bytes is exclusively a source-side `install.py` operation from
an independently verified release. For a current protocol-v2 listener, that
source-side transaction uses the same handoff protocol after committing the
admitted release projection. Installed control exposes no arbitrary stage path,
release upgrade, or controller-only partial apply.

`governance.py --json` is read-only. It reports manifest integrity, route
authority, verified listener identity, and the startup-frozen aggregate SHA-256
of the loaded serving payload when
the loopback listener is reachable. It does not inspect or change AIGW settings,
Codex conversation state, credentials, or the proxy lifecycle.

### Reliability evidence

`status --json` also reports the listener's loopback-only, process-local
`runtime` snapshot when the verified service is reachable. It includes counters
for completed and incomplete streams, pre-content reconnects, bounded
`response_failed` and exact input-variant recovery, encrypted-replay stripping,
and classified upstream outcomes. `last_failure` records only a stable class
and Unix timestamp. It
never includes request bodies, tokens, credentials, headers, prompts, or
upstream error payloads. The endpoint is read-only and is available only at
`GET /healthz` on the loopback listener; it is not a remote monitoring API.
`runtime.draining` and `runtime.active_responses` together expose the lifecycle
barrier: while draining is true, no new Responses request may enter the active
set. `runtime.drain_lease_remaining_seconds` makes the fail-open lease visible.
The `handoff_*`, `pid`, `serving_payload_sha256`,
`release_receipt_sha256`, `payload_manifest_sha256`, and `accepting` fields bind
a protocol-v2 transition to one process, transaction, and released payload.
The loopback-only
`POST /control/handoff` endpoint and its child pipe protocol are lifecycle
internals, not general APIs.
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
inferred incident. A changed release, serving-payload digest, or listener restart
starts a new window. In a comparable window, local payload/listener faults and
new local stream failures are incidents; upstream `empty_response`, retryable
5xx, `response_failed`, and exact input-variant validation are observations
below three events and incidents at three or more. New `proxy_draining`
rejections are distinct from upstream
failures; when an operator has deliberately initiated maintenance, pass
`--allow-drain` to classify that delta as `observe`. The optional state file
contains only normalized counters, runtime identity, uptime, and observation
time. It never stores request bodies, responses, tokens, headers, prompts,
paths from the status payload, or upstream error payloads.

### One-time legacy bootstrap

A listener released before protocol-v2 handoff cannot perform an atomic socket
transfer. Source-side installation therefore refuses replacement by default.
Only an explicitly authorized install with `--allow-legacy-bootstrap` may use
the compatibility path. It first verifies the installed manifest and exactly
one listener, then requires that PID to remain at zero active Responses for the
bounded quiet window before committing the admitted release transaction.
Activity, health loss, timeout, or PID change refuses the mutation. Once the
protocol-v2 successor proves its released aggregate identity, future payload
changes use source-side transactional handoff and installed-control operations
remain same-payload reloads.

If an urgent, separately authorized interruption is unavoidable,
`--force-legacy-bootstrap` may be combined with `--allow-legacy-bootstrap` on
the source-side installer. It still requires manifest integrity and exactly one
verified legacy listener. The flag is rejected without the allow flag, is not
available to installed-control `reload`, and is never a normal operating mode.

### Log retention and diagnostic safety

The proxy and watchdog write structured operational events only. They do not
persist request bodies, credentials, headers, prompts, query values, or raw
upstream payloads. Each log has a bounded rotating retention window; the default
is four 4 MiB proxy segments and three 512 KiB watchdog segments, including the
active segment. Oversized legacy segments are discarded without being copied or
read into evidence. Each admitted source-side installation also removes the retired
`reject-*.json` raw request-capture files without reading or preserving them.
Native macOS service stdout and stderr are deliberately discarded so they cannot
become an unbounded second logging channel.

Set a durable retention policy at installation time:

```bash
python3 install.py \
  --tag "v$(cat VERSION)" \
  --gitlab-remote "$GITLAB_REMOTE" --gitlab-api-base "$GITLAB_API_BASE" \
  --gitlab-repo "$GITLAB_REPOSITORY" --github-remote "$GITHUB_REMOTE" \
  --github-repo HengYangDS/codex-dmx-proxy \
  --gitlab-anchor packaging/release/gitlab-allowed-signers \
  --github-anchor packaging/release/github-allowed-signers \
  --trust-anchor "$DMX_RELEASE_TRUST_ANCHOR" \
  --proxy-log-max-bytes 4194304 \
  --proxy-log-backup-count 3 \
  --watchdog-log-max-bytes 524288 \
  --watchdog-log-backup-count 2
```

The selected bounds are rendered into the native user service. Changing them
requires another released, publication-proven source-side installation; a
same-payload `reload` does not change service configuration.

## Design

```text
Codex -> 127.0.0.1:8791 -> verified Responses endpoint
           |
           +-- watchdog supervised by the native user service
```

The proxy preserves end-to-end headers and credentials while normalizing
transport-owned headers such as Host, Content-Length, and Accept-Encoding. For
`POST /responses`, it may remove stale top-level reasoning replay items,
unreplayable local images, malformed legacy encrypted-content shells, and
`reasoning.encrypted_content` from `include`. It fails open: if a body cannot
be parsed and safely reserialized, it forwards the original bytes unchanged.

Bounded retries apply only to explicitly classified upstream conditions. An
ordinary client-side 400, an encrypted-content validation error, and unknown
rejections are returned unchanged.

## Diagnose

| Symptom | First check | Boundary |
| --- | --- | --- |
| Encrypted replay error | `control.py status --json` | Confirm a healthy listener and enabled route before investigating history. |
| Upstream `response_failed` | `control.py status --json` | After the explicit 400, the proxy makes up to three strictly shrinking, pair-safe fallback attempts. If all are explicitly rejected, it may send one safely smaller dialogue-only attempt and then returns retryable 503 with `Retry-After: 3`; unrelated 400 responses remain unchanged. |
| Exact `Invalid 'input'` validation error | `control.py status --json` | The proxy may send one current-dialogue fallback. Diagnostics contain only bounded type counts, pairing state, a categorical shape hash, and the first locally detectable incompatibility; no request values or unknown labels are logged. |
| DMX HTTP 477 `empty_response` | `control.py status --json` | The proxy may send one dedicated semantic-preserving fallback. If projection is unsafe or that follow-up fails, both streaming and non-streaming requests receive standard HTTP 503 with `Retry-After: 3`; unrelated 477 responses remain unchanged. |
| SSE closes before completion | `control.py status --json` | The proxy retries only before sending substantive bytes downstream. If that bounded pre-content budget is exhausted, it returns retryable HTTP 503 with `Retry-After: 3` rather than an empty successful stream. |
| Need current reliability evidence | `control.py status --json` | Inspect the secret-free `runtime` snapshot; it proves listener-local counters, not recovery of a historical conversation. |
| Need a windowed incident decision | `scripts/observe-reliability.py --status-file <snapshot> --state <baseline>` | Compare only the same running payload; the tool is read-only and never reloads the listener. |
| Client ignores a route change | Client configuration lifecycle | A running client may need its normal reload; the proxy does not restart it. |

Logs are written under `~/.codex/log/`. They record bounded operational facts:
stable classifications, request identifiers, sanitized paths, byte lengths,
recovery stages, and exact retained/dropped item counts. Input diagnostics use
bucketed counts and closed labels. The proxy does not persist request bodies,
credentials, headers, prompts, query values, unknown names, or raw upstream
failures.

## Configure

The generated service supplies safe defaults. Use install arguments rather than
editing a generated service definition:

```bash
python3 install.py \
  --tag "v$(cat VERSION)" \
  --gitlab-remote "$GITLAB_REMOTE" --gitlab-api-base "$GITLAB_API_BASE" \
  --gitlab-repo "$GITLAB_REPOSITORY" --github-remote "$GITHUB_REMOTE" \
  --github-repo HengYangDS/codex-dmx-proxy \
  --gitlab-anchor packaging/release/gitlab-allowed-signers \
  --github-anchor packaging/release/github-allowed-signers \
  --trust-anchor "$DMX_RELEASE_TRUST_ANCHOR" \
  --port 8801 \
  --upstream https://your.responses.endpoint
```

See [`config.example`](config.example) for the supported environment variables.

## Verify a source checkout

```bash
python3 scripts/check_release_metadata.py --prepare-release
python3 scripts/check_markdown_presentation.py
python3 scripts/test_release_metadata.py
PYTHON=python3.12 RUFF=ruff TY=ty sh scripts/run-python-quality.sh
for py in python3.12 python3.13 python3.14; do
  "$py" -m compileall -q codex_dmx_proxy watchdog install.py uninstall.py control.py governance.py tests scripts
  "$py" scripts/run-python-tests.py
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
