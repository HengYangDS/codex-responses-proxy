# Codex Responses Proxy

Licensed under [MIT](LICENSE). Forge coordinates and publication actors are
deployment context, not product identity.

Codex Responses Proxy is a local, loopback-only compatibility adapter for third-party
OpenAI Responses endpoints. It repairs replay incompatibilities at the network
edge without rewriting Codex conversations, SQLite state, JSONL archives, or
per-conversation model selection.

It is intentionally narrow:

- **Codex Desktop** owns conversations and the model selected for each one.
- **AIGW** owns provider configuration, credentials, endpoint selection, and
  projection to Codex profiles.
- **Codex Responses Proxy** owns outbound Responses compatibility, its released
  payload and deployment, and native supervision.

## When to use it

Use this adapter only when a verified third-party Responses endpoint rejects
replayed Codex state, for example:

- `encrypted content could not be verified`;
- `Missing required parameter: ... encrypted_content` from a legacy malformed
  replay block;
- a local image reference that the upstream endpoint cannot fetch;
- a transient `invalid_payload`, gateway timeout, or pre-content SSE interruption;
- a classified DMX HTTP 477 `empty_response` (one exact retry of the already
  projected request);
- an upstream HTTP 429 rate limit (no proxy retry; the first response is relayed
  and only that provider enters a bounded process-local cooldown);
- an explicit upstream `response_failed` execution rejection of replay context;
- the exact observed `Invalid 'input'` union validation contract.

Before every upstream attempt, the adapter projects replay onto a closed,
provider-portable grammar. It removes provider response/conversation/cache
bindings, reasoning and stored-item references, provider-issued item IDs,
search state, and encrypted reasoning, agent, and tool-output content. It keeps
text dialogue, agent author/recipient/phase context, complete function and
custom-tool pairs, and replayable remote images. A correctly paired tool result
with no textual output receives an explicit empty-result marker; an
encrypted-only retained agent or tool result receives a distinct omission
marker, and no ciphertext is claimed to be decrypted. Empty ordinary dialogue
and unknown or malformed replay structures return a local HTTP 400 before any
upstream request. The outbound copy always uses `store=false`; continuity comes
from projected dialogue and complete tool relationships, never from a third-
party provider's stored response or item IDs.

Only exact `POST /<provider>/v1/responses` targets and exact read-only
`GET /<provider>/v1/models` targets are admitted. A model-catalog request is
relayed once to the same manifest-owned upstream without request or response
projection, Responses admission, cooldown, retry, or provider-policy recovery.
Encoded path material, dot segments, duplicate separators, lookalike suffixes,
absolute targets, fragments, unsupported methods, and unrelated endpoints are
rejected before remote I/O. Successful non-stream Responses are buffered within
an eight-MiB integrity limit before downstream commitment,
required to be valid terminal JSON (`completed` or `incomplete`), and projected
with the same ciphertext-removal rules as SSE. Unknown residual ciphertext,
empty, truncated, oversized, malformed, or non-terminal HTTP 2xx bodies become
a local retryable 503; partial success bytes are never committed.

DMX HTTP 477 handling does not own another replay grammar. When the exact
`empty_response` contract matches, the proxy retries the current upstream
attempt bytes once. Those bytes have already passed the provider-neutral
projection, including any earlier bounded `response_failed` compaction. The
retry therefore cannot restore provider IDs, ciphertext, search state, or an
older, larger request body.

For a structured upstream error whose `type` is present and whose `code` is
exactly `response_failed`, it first makes up to three
strictly smaller fallbacks that each remove only the oldest contiguous,
tool-pair-safe input prefix, retain the latest user context, and drop the stale
`prompt_cache_key` from fallback requests only. If the upstream explicitly rejects
those pair-safe fallbacks as well, the proxy may make one final dialogue-only
request: the latest developer or system instruction before the active request,
where present, plus the latest user request, without assistant or tool replay. It
only sends that final request when it is safely smaller than the rejected replay.
Incidental message prose does not trigger semantic recovery. Exhaustion, loops,
or unsafe failures are returned as standard retryable HTTP
503 with `Retry-After: 3`, so the client may apply its own retry policy.
It is not a replacement for an upstream service with persistent failures.

HTTP 429 is outside the generic transient retry loop. The proxy relays the first
rate-limit status, body, and eligible headers without sleeping or opening a
second upstream request for that client attempt. A valid `Retry-After` sets a
process-local cooldown for only the selected provider, capped at five minutes;
an absent, invalid, zero, or expired value uses a five-second fallback. Requests
arriving during that cooldown receive local HTTP 429 without upstream I/O, while
other providers remain independent. Overlapping failures can extend an active
cooldown but cannot shorten it. The default Responses concurrency is 8 and
remains configurable through the validated runtime setting; it is a burst
guardrail, not a claim about a provider's undocumented quota.

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
- A verified third-party Responses endpoint. The adapter never stores an API key.
- One exact signed release checkout and its absolute trust-anchor file stored
  outside that checkout. Installation does not require Forge credentials.

## Install

Installation is a post-release operation. Start from the exact clean checkout
whose `HEAD` is the signed annotated `v<VERSION>` tag. The installer requires
that clean state before admission and repeats the check before minting the
payload capability. Release operators independently verify both Forge planes
and may retain the verifier's JSON result as publication evidence:

```bash
python3 tools/release/verify.py \
  --tag "v$(cat VERSION)" \
  --gitlab-remote "$GITLAB_REMOTE" \
  --gitlab-api-base "$GITLAB_API_BASE" \
  --gitlab-repo "$GITLAB_REPOSITORY" \
  --github-remote "$GITHUB_REMOTE" \
  --github-repo "$GITHUB_REPOSITORY" \
  --gitlab-anchor "$GITLAB_ANCHOR" \
  --github-anchor "$GITHUB_ANCHOR" \
  --policy "$PUBLICATION_JOB_POLICY" \
  --json > "$PUBLICATION_EVIDENCE_PATH"
```

The verifier fails closed unless both provider-native signed tags, required CI
jobs, and formal Release records bind to the same source tree. Job policy and
Forge trust anchors are explicit operator inputs outside the checkout; neither
is product source. They do not replace the installer's independent release
trust anchor, which must be an absolute regular file outside the checkout. JSON
is evidence only and cannot authorize installation. Installation consumes one
selected signed release source and has no GitLab, GitHub, CI, or release-record
dependency:

```bash
python3 -m codex_responses_proxy.commands.install \
  --trust-anchor "$CODEX_RESPONSES_PROXY_RELEASE_TRUST_ANCHOR"
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

If a prior source-side install retained an exact `recovery_required`
transaction, a newer verified installer can use `--rollback-recovery` to
restore that recorded prior projection only while the accepting listener still
reports the rollback release, serving digest, and receipt digest, reports the
manifest digest of the fully verified candidate committed on disk, remains idle,
and is the sole PID bound to the installed entrypoint. A
protocol-v2 listener whose released upgrade logic is known unable to advance
may then be replaced with the explicit `--force-v2-bootstrap` authorization.
These options do not weaken live
publication, source, payload, process, or successor proof.

### Client endpoint configuration

The installer never reads or writes AIGW or client configuration. After the
released proxy is installed, a consumer may select its fixed loopback namespace
through that consumer's own control plane. For example, AIGW may project:

```bash
port="${CODEX_RESPONSES_PROXY_PROXY_PORT:-8792}"
aigw account edit dmxapi --openai-url "http://127.0.0.1:${port}/dmxapi/v1"
aigw account edit ucloud --openai-url "http://127.0.0.1:${port}/ucloud/v1"
aigw account edit aihubmix --openai-url "http://127.0.0.1:${port}/aihubmix/v1"
aigw sync --dry-run --json
aigw sync --json
```

Port 8792 is only the product default. Installation, control, and removal accept
an explicit `--port`, and the supervised runtime consumes
`CODEX_RESPONSES_PROXY_PROXY_PORT`; no consumer is required to use 8792.

The fixed namespaces map only to manifest-owned HTTPS origins; request headers,
bodies, and query parameters cannot select another host. AIGW continues to own
credentials, account selection, storage policy, and client projection. The two
products have no package, process, filesystem, or configuration dependency.

### Apply a route change

An already-running Codex client may cache configuration. Let the client reload
configuration through its normal lifecycle before expecting a changed route to
take effect. Do not create a new conversation or alter history merely to apply
a route change.

## Operate

```bash
# Read-only runtime evidence from the installed product directory
python3 -m codex_responses_proxy.commands.control status --json

# Hand off one verified protocol-v2 listener without closing its socket
python3 -m codex_responses_proxy.commands.control reload --json

# Remove the product-owned service
python3 -m codex_responses_proxy.commands.uninstall

# Also remove the generated runtime payload
python3 -m codex_responses_proxy.commands.uninstall --purge
```

Uninstall never reads or changes consumer endpoint configuration. Before any
payload mutation, native service removal must report `absent`, and every watchdog and
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

Changing payload bytes is exclusively a source-side
`python3 -m codex_responses_proxy.commands.install` operation from an independently
verified release. For a current protocol-v2 listener, that
source-side transaction uses the same handoff protocol after committing the
admitted release projection. Installed control exposes no arbitrary stage path,
release upgrade, or controller-only partial apply.

`python3 -m codex_responses_proxy.commands.control status --json` reports
manifest integrity, verified listener identity, transaction state, and the
startup-frozen aggregate SHA-256 of the loaded serving payload when the loopback
listener is reachable. It does not
inspect AIGW settings, client configuration, conversation state, or credentials.

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
endpoints are lifecycle internals used by the installed control command, not general APIs.

For a repeatable, privacy-bounded trend decision, use the source-side observer
with two or more comparable snapshots. It consumes the JSON that `status`
already emits; it neither contacts the listener nor changes its lifecycle:

```bash
status_file="$(mktemp)"
python3 -m codex_responses_proxy.commands.control status --json > "$status_file"
python3 tools/reliability/observe.py \
  --status-file "$status_file" \
  --state "$CODEX_RESPONSES_PROXY_OBSERVER_STATE"
rm -f "$status_file"
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
the compatibility path. It verifies the exact supported historical manifest,
derives the old entrypoint from that inventory, and binds exactly one listener
PID to that path. After the bounded zero-active quiet window, the transaction
snapshots old owned bytes, installs the candidate, terminates only the bound
process, replaces native supervision, and finalizes only after exact successor
identity proof. Activity, health loss, timeout, or PID change refuses mutation.
After old-process exit, any service/startup failure restores the old owned bytes,
old supervision entrypoint, and an accepting historical listener before the
operation reports rollback. Future payload changes then use
protocol-v2 handoff; installed control remains same-payload only.

If an urgent, separately authorized interruption is unavoidable,
`--force-legacy-bootstrap` may be combined with `--allow-legacy-bootstrap` on
the source-side installer. It still requires manifest integrity and exactly one
verified legacy listener; it skips only the quiet wait. The flag is rejected
without the allow flag, is not available to installed-control `reload`, and is
never a normal operating mode.

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
python3 -m codex_responses_proxy.commands.install \
  --trust-anchor "$CODEX_RESPONSES_PROXY_RELEASE_TRUST_ANCHOR" \
  --proxy-log-max-bytes 4194304 \
  --proxy-log-backup-count 3 \
  --watchdog-log-max-bytes 524288 \
  --watchdog-log-backup-count 2
```

The selected bounds are rendered into the native user service. Changing them
requires another signed-release source-side installation; a
same-payload `reload` does not change service configuration.

## Design

```text
Codex/AIGW -> 127.0.0.1:<configured-port>/dmxapi/v1  -> DMXAPI
           -> 127.0.0.1:<configured-port>/ucloud/v1  -> UCloud/Azure
           -> 127.0.0.1:<configured-port>/aihubmix/v1 -> AIHubMix
                      |
                      +-- watchdog supervised by the native user service
```

The proxy preserves end-to-end headers and credentials while normalizing
transport-owned headers such as Host, Content-Length, and Accept-Encoding. For
`POST /responses`, normal outbound projection removes every known
provider-bound carrier. Request replay is fail-closed: malformed JSON, unknown
item/content types, and invalid tool pairing return a bounded local HTTP 400.
SSE rewriting is event-local and atomic; an event that cannot be safely parsed
or serialized is relayed unchanged rather than partially mutated.

Bounded retries apply only to explicitly classified upstream conditions. An
ordinary client-side 400, an encrypted-content validation error, and unknown
rejections are returned unchanged.

## Diagnose

| Symptom | First check | Boundary |
| --- | --- | --- |
| Missing `rs_` item or encrypted replay error | `python3 -m codex_responses_proxy.commands.control status --json` | Confirm the account uses its scoped proxy route. The normal request projection removes provider IDs and ciphertext without editing history. |
| Error after provider switch | Consumer control-plane diagnostics | The consumer must select one manifest-defined scoped route; a direct upstream endpoint bypasses portability. AIGW is one optional control plane, not a proxy dependency. |
| Upstream `response_failed` | `python3 -m codex_responses_proxy.commands.control status --json` | After the explicit 400, the proxy makes up to three strictly shrinking, pair-safe fallback attempts. If all are explicitly rejected, it may send one safely smaller dialogue-only attempt and then returns retryable 503 with `Retry-After: 3`; unrelated 400 responses remain unchanged. |
| Exact `Invalid 'input'` validation error | `python3 -m codex_responses_proxy.commands.control status --json` | The proxy may send one current-dialogue fallback. Diagnostics contain only bounded type counts, pairing state, a categorical shape hash, and the first locally detectable incompatibility; no request values or unknown labels are logged. |
| DMX HTTP 477 `empty_response` | `python3 -m codex_responses_proxy.commands.control status --json` | The proxy retries the already projected current attempt bytes exactly once. If that retry fails, both streaming and non-streaming requests receive standard HTTP 503 with `Retry-After: 3`; unrelated 477 responses remain unchanged. |
| SSE closes before completion | `python3 -m codex_responses_proxy.commands.control status --json` | The proxy retries only before sending substantive bytes downstream. If that bounded pre-content budget is exhausted, it returns retryable HTTP 503 with `Retry-After: 3` rather than an empty successful stream. |
| Client reports `local proxy overloaded: timed out waiting` | `python3 -m codex_responses_proxy.commands.control status --json` | One provider route is saturated, not the whole process; the message names the route and both limits. A queued turn waits the bounded local queue timeout, then receives retryable HTTP 503 with `Retry-After: 5`. The holding turn is bounded only by the total upstream stream deadline, so that hint is a floor rather than a prediction. |
| Legitimate long turns keep exhausting that queue wait | `python3 -m codex_responses_proxy.commands.control status --json` | The default queue wait now covers one total upstream stream deadline, so a waiter is not denied while its holder is still running; a waiting request also holds no process-wide slot, because the route slot is acquired first. A listener installed before this default still pins the old value in its unit, because the unit is rendered at install time and the install exposes no flag for this setting — reinstall to re-render it. To deviate from the default, set `CODEX_RESPONSES_PROXY_RESPONSES_QUEUE_TIMEOUT` in the unit's environment; exporting it in a shell does not reach a supervised listener. |
| Need current reliability evidence | `python3 -m codex_responses_proxy.commands.control status --json` | Inspect the secret-free `runtime` snapshot; it proves listener-local counters, not recovery of a historical conversation. |
| Need a windowed incident decision | `tools/reliability/observe.py --status-file <snapshot> --state <baseline>` | Compare only the same running payload; the tool is read-only and never reloads the listener. |
| Client ignores a route change | Client configuration lifecycle | A running client may need its normal reload; the proxy does not restart it. |

Logs are written under the platform-native `codex-responses-proxy` state directory. They record bounded operational facts:
stable classifications, request identifiers, sanitized paths, byte lengths,
recovery stages, and exact retained/dropped item counts. Input diagnostics use
bucketed counts and closed labels. The proxy does not persist request bodies,
credentials, headers, prompts, query values, unknown names, or raw upstream
failures.

## Configure

The generated service supplies safe defaults. Use install arguments rather than
editing a generated service definition:

```bash
python3 -m codex_responses_proxy.commands.install \
  --trust-anchor "$CODEX_RESPONSES_PROXY_RELEASE_TRUST_ANCHOR" \
  --port 8801
```

Portable data, state, listener, timeout, concurrency, and log-retention
settings are declared and validated by
`codex_responses_proxy.runtime.config`. Normal installations persist explicit
installer arguments into native supervision; environment overrides are for
direct runtime composition and tests, not a second configuration file.

## Verify a source checkout

```bash
python3 tools/release/metadata.py --prepare-release
python3 tools/quality/markdown.py
python3 tests/release/test_metadata.py
PYTHON=python3.12 sh tools/quality/run.sh
for py in python3.12 python3.13 python3.14; do
  "$py" tools/quality/tests.py --compile
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
