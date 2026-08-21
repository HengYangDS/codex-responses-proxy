# Authority and Runtime Boundary

Codex Responses Proxy is a local Responses data plane. It normalizes outbound
traffic and owns its native service lifecycle. It does not own client state or
provider selection.

## Product position

The proxy is a narrow compatibility edge for proven Responses gaps. It is not
a general AI gateway, provider catalog, configuration switcher, billing plane,
or agent runtime. Direct provider access remains the default whenever the
client and provider already share a sound protocol.

Its value is the combination of a small authority surface and strong replay
semantics: provider selection stays in the client control plane, while the
proxy makes only the minimum transport changes needed for stateless,
provider-portable Responses traffic.

## Product graph

```mermaid
flowchart LR
    C["Codex"] --> P["Loopback proxy"]
    P --> R["Provider-scoped route"]
    R --> U["Third-party Responses API"]
    S["Client control plane"] -. configures .-> C
    S -. selects URL .-> P
```

## Authority

| Owner | Authoritative state |
| --- | --- |
| Codex | Conversations, tool state, JSONL, SQLite, stored items, model metadata |
| Client control plane | Credentials, provider selection, and client endpoint configuration |
| Proxy source and release | Provider manifest, protocol policy, native bundle, lifecycle contract |
| Installed proxy | Manifest-owned payload and native service projection |
| Provider | Model execution, quota, and upstream availability |
| GitLab / GitHub | Independent CI, tag, Release, and asset records |

The proxy repairs compatibility only at the network edge. It never rewrites a
conversation or reads another product's configuration.

## Semantic packages

```mermaid
flowchart TD
    CLI["cli"] --> LIFE["lifecycle"]
    CLI --> VIEW["presentation"]
    LIFE --> SERVICE["service"]
    SERVICE --> RELAY["relay"]
    RELAY --> PROTOCOL["protocol"]
    RELAY --> PROVIDERS["providers"]
```

| Package | Owns |
| --- | --- |
| `cli` | Public grammar, command composition, human/JSON selection |
| `providers` | Manifest-defined routes and optional pure policies |
| `protocol` | Closed provider-portable request and response grammar |
| `relay` | Admission, upstream exchange, retries, cooldown, SSE and HTTP integrity |
| `service` | Listener process, health, structured logs, control and handoff protocol |
| `lifecycle` | Artifact trust, payload transaction, supervision, install, reload, uninstall |

Dependencies point toward semantic owners. No package may infer provider
behavior from a name when the manifest or explicit policy contract owns it.

## Provider routing

The released manifest is the sole provider registry.

```text
/<provider>/v1/responses
/<provider>/v1/models
```

- Responses routes enter projection, recovery, cooldown, and integrity checks.
- Models routes are transparent authenticated GET relays.
- Unscoped, encoded, ambiguous, or unrelated paths fail before remote I/O.
- Headers, bodies, and query parameters cannot select an upstream host.
- Adding an ordinary provider changes one manifest table.

## Provider admission

Provider integration follows one ordered test:

```mermaid
flowchart TD
    D["Try direct endpoint"] --> W{"Wire compatible?"}
    W -->|Yes| N["No proxy change"]
    W -->|No| M["Add manifest route"]
    M --> T["Run portable contract tests"]
    T --> G{"Exact gap remains?"}
    G -->|No| R["Manifest-only admission"]
    G -->|Yes| E["Capture minimal failing payload"]
    E --> P["Add the smallest pure policy"]
```

- Native Responses that works directly needs no proxy change.
- A standard Bearer endpoint that needs only portable projection adds one
  manifest entry.
- A reproducible wire difference adds one narrow pure policy and its regression
  evidence.
- Request signing or another stateful authentication exchange requires a
  separate authentication boundary.
- A different invocation protocol requires an explicit protocol Adapter or
  product decision.

A provider name never creates behavior. The released manifest selects a route
and, when necessary, an explicitly declared policy. This keeps ordinary
Provider admission data-driven and makes a new policy pay for its permanent
maintenance cost with exact evidence.

AWS Bedrock illustrates the distinction. A Mantle endpoint that already speaks
OpenAI Responses can be admitted as an ordinary route. Native IAM/SigV4 or
Converse/InvokeModel would require explicit authentication and protocol work;
it must not be represented as a Bearer-compatible route.

## Responses projection

```mermaid
sequenceDiagram
    participant Codex
    participant Proxy
    participant Provider

    Codex->>Proxy: Responses request
    Proxy->>Proxy: Validate route and closed input grammar
    Proxy->>Proxy: Remove provider-bound replay state
    Proxy->>Provider: store=false portable request
    Provider-->>Proxy: JSON or SSE response
    Proxy->>Proxy: Validate integrity without changing response bytes
    Proxy-->>Codex: Committed response or bounded failure
```

The request projection removes response, conversation, cache, provider-issued
item, search, and encrypted-reasoning bindings. It retains portable dialogue
and complete tool relationships. Unknown or unsafe structures fail locally.

The live-response boundary preserves encrypted control content needed for the
current turn. Portability is applied only if a later request replays that
output. Empty, truncated, malformed, oversized, or non-terminal success bodies
become a retryable local `503`; partial success bytes are not committed.

## Recovery ownership

| Condition | Bounded behavior |
| --- | --- |
| DMXAPI `477 empty_response` | Retry the already-projected bytes once |
| `response_failed` | Strictly shrinking pair-safe attempts, then at most one dialogue-only attempt |
| Invalid `input` union | One smaller current-dialogue attempt |
| Pre-content stream interruption | Retry only before substantive downstream commitment |
| `429` | Relay once; provider-scoped cooldown; no global queue |

Each recovery consumes the same provider-portable request owner. No recovery
path restores provider IDs, ciphertext, or an older request body.

Retries are bounded by the semantic failure class. The proxy does not provide
cross-provider fallback, a global work queue, or hidden model substitution.
Those behaviors would combine transport ownership with routing policy and make
provider switching less observable.

## Lifecycle transaction

```mermaid
stateDiagram-v2
    [*] --> Admitted
    Admitted --> Prepared
    Prepared --> Committed
    Committed --> Serving: exact successor proof
    Committed --> RecoveryRequired: outcome unconfirmed
    Prepared --> RolledBack: pre-commit failure
    Serving --> [*]
```

Artifact admission verifies the release asset, complete bundle inventory, and
external trust anchor. The installer commits the verified projection, then
prewarms that exact executable, rebinds native supervision to it, and only then
requests listener handoff while rollback remains available. The handoff child
owns listener transfer and runtime identity; it does not mutate launchd,
systemd, or Task Scheduler state.
The same transaction projects one native user-command link and records its
exact path in installed state. Rollback and uninstall therefore do not re-derive
ownership from a later shell environment. Installation finalizes only after one
listener proves the expected release, payload digest, manifest digest, receipt
digest, PID, and accepting state.

Reload is same-payload handoff. Upgrade is install. Uninstall removes native
supervision first, proves owned listener exit, removes only the recorded command
link while it still targets the installed executable, then optionally removes
only manifest-owned payload files.

## Human and machine surfaces

The CLI projects one result model:

| Surface | Contract |
| --- | --- |
| Human | Scannable lifecycle state and one safe next action |
| JSON | Stable, secret-free machine evidence |
| Logs | Structured bounded events; no prompts, Tokens, headers, bodies, or raw upstream payloads |

Runtime evidence proves only the installed listener. It does not prove client
configuration, provider billing, or recovery of a historical conversation.
