## Why

AIGW validates an OpenAI-compatible account and discovers its models through
`GET <endpoint>/models`. The selected local compatibility adapter accepts only
Responses requests today, so the otherwise valid provider-scoped loopback URL
returns local 404 before either AIGW health checks or catalog discovery can
reach the configured upstream.

## What Changes

- Admit only exact `GET /<provider>/v1/models` requests beside the existing
  exact Responses route.
- Relay that read-only request to the same release-owned provider upstream with
  the client-supplied authentication headers and no request transformation.
- Keep `/responses` projection, recovery, concurrency, and cooldown behavior
  exclusive to Responses traffic; reject all other paths and methods locally.
- Document the limited catalog endpoint as an external-consumer compatibility
  surface, without giving the proxy ownership of AIGW configuration or catalog
  policy.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `provider-portable-responses`: subject=provider-scoped read-only model-catalog
  routing; reuse=extend; change=modify; add exact `GET /<provider>/v1/models`
  admission beside the Responses route while retaining a closed HTTP boundary;
  facet:lifecycle=request,discovery,release,installation,acceptance;
  facet:surface=registry,transport,listener,test,docs,openspec,claim,evidence;
  facet:authority=source,test,docs,openspec,claim,evidence.

## Out of Scope

- Changing AIGW accounts, endpoints, credentials, client projections, or model
  selection.
- Filtering, caching, parsing, or synthesizing a provider catalog.
- Adding generic `/<provider>/v1/*` forwarding, a new proxy lifecycle action,
  or a direct endpoint substitution.
- Editing Codex JSONL, SQLite, archives, transcripts, or model metadata.

## Impact

Affected code: provider route resolution, loopback transport dispatch, and
route-contract tests. AIGW configuration, credentials, client projections,
conversation records, provider selection, and proxy lifecycle are unchanged.
Local tests prove request routing only; hosted CI, publication, installed
release upgrade, and live AIGW recovery remain separate acceptance stages.
