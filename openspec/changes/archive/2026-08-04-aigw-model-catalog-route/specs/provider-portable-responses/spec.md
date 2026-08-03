## MODIFIED Requirements

### Requirement: Provider routes admit only exact Responses and model-catalog targets

The listener SHALL expose provider-scoped loopback Responses targets and exact
read-only model-catalog targets for `dmxapi`, `ucloud`, and `aihubmix`. Each
namespace SHALL resolve only exact `POST /<provider>/v1/responses` targets with
an optional query to its release-owned HTTPS upstream mapping, or exact
`GET /<provider>/v1/models` targets with an optional query to that same mapping.
Responses targets SHALL retain their existing compatibility projection and
recovery behavior. Model-catalog targets SHALL relay once without request-body
or response projection, Responses admission, cooldown, retry, or
provider-policy recovery. Encoded path material, dot segments, duplicate
separators, lookalike suffixes, fragments, absolute targets, unsupported
methods, and unrelated endpoints SHALL be rejected locally. A downstream
request SHALL NOT supply or override an upstream URL or host.

#### Scenario: AIGW selects each governed provider

- **WHEN** AIGW sends otherwise equivalent Requests traffic to
  `/dmxapi/v1/responses`, `/ucloud/v1/responses`, or
  `/aihubmix/v1/responses`
- **THEN** the proxy sends it only to the matching DMXAPI, UCloud/Azure, or
  AIHubMix HTTPS upstream
- **AND** credentials continue to come from the AIGW-managed client request.

#### Scenario: A client discovers a selected provider catalog

- **WHEN** a client sends `GET /dmxapi/v1/models`, `/ucloud/v1/models`, or
  `/aihubmix/v1/models`
- **THEN** the proxy makes one request only to the matching release-owned
  upstream `/v1/models` path
- **AND** it relays authentication, upstream status, eligible headers, and body
  without Responses replay transformation or recovery.

#### Scenario: A caller uses an unknown namespace

- **WHEN** a request path does not match a control endpoint, one of the three
  canonical Responses targets, one of the three canonical model-catalog
  targets, or the bounded DMX migration route
- **THEN** the proxy rejects it locally
- **AND** it performs no remote network request.
