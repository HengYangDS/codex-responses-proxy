## Context

See `proposal.md`. The candidate branch owns two later Responses-only contracts:
route-local queue timeout presentation with `Retry-After: 5`, and a one-turn total
SSE deadline. The catalog lane adds a closed `models` resource whose route must not
enter those Responses-only policies. The native rebase correctly conflicts because
both changes replace the same dispatcher.

## Goals / Non-Goals

**Goals:**

- Preserve the candidate's current `POST /responses` admission, cooldown, and
  SSE behavior byte-for-byte except for structural extraction needed to dispatch
  catalog reads.
- Dispatch only `GET /models` to the catalog relay, which is transparent and
  single-attempt.
- Bind all final source evidence to the rebased head.

**Non-Goals:**

- No generic forwarding, AIGW modification, proxy installation, or live runtime
  restart during this integration.
- No alteration of the already archived original catalog-change record.

## Decisions

### Responses remains an explicit branch

The reconstructed dispatcher checks `(method, resource)` and routes `POST
responses` to the candidate's Responses flow. The candidate queue timeout text,
retry header, and the stream's total-deadline mechanics remain in that flow.

Alternative: force catalog traffic through `Exchange` and reuse the Responses
flow. Rejected because it would couple catalog discovery to capacity and recovery
state.

### Catalog remains a separate transparent branch

`GET models` uses the release-owned upstream URL and common hop-by-hop header
filtering, but creates no `Exchange`, does not read a request body, and cannot
invoke replay, cooldown, admission, retry, or recovery.

### Evidence is rebased, not copied forward

The claim semantic digest and chronicle report the exact new head and rerun proof.
The original archived catalog dossier remains immutable historical evidence.

## Risks / Trade-offs

- [Structural extraction drifts from the candidate route behavior] → assert the
  existing deadline and queue-timeout contracts alongside catalog contracts.
- [Catalog accidentally gains Responses state] → retain negative contracts that
  prove no admission/cooldown/replay call occurs for `GET /models`.
- [Fresh proof is mistaken for installed runtime acceptance] → keep installation
  and AIGW acceptance explicitly out of this carrier.
