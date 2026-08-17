# Evidence Policy

Status: canonical.

A result supports acceptance only when its scope, verifier, exact source
revision, evidence, and limit are explicit. The repository has no tracked
`evidence/` taxonomy: source, tests, Git history, OpenSpec archives, release
artifacts, and ETHOS-selected Attestations already own the required facts.

Claims are propositions inside a bounded result, not a file family. Historical
explanation belongs in the OpenSpec archive, a decision record, the Changelog,
or Git history; Chronicle is not a separate evidence primitive.

- **Source evidence:** unit tests, compile checks, metadata checker, and CI.
- **Runtime evidence:** installed payload manifest,
  `codex-responses-proxy status --json`, verified listener identity, bounded
  runtime counters, and a bounded reload receipt when requested.
- **User-visible evidence:** a successful response in the original failing
  conversation is distinct from transport health.

Provider-portability acceptance requires the unchanged original conversation
to complete at least two turns on each leg of
`DMXAPI -> UCloud -> AIHubMix -> DMXAPI`. Before the sequence, record the exact
JSONL length and SHA-256 of that immutable prefix plus metadata for the relevant
SQLite stores and per-conversation model selection. After every leg, verify the
same prefix byte-for-byte and re-observe the metadata. New JSONL suffix bytes
are expected conversation output; rewriting any baseline byte or changing the
observed metadata fails acceptance. A proxy health check, direct endpoint smoke,
or a new conversation cannot substitute for this result.

Do not treat a green local process, a new clean conversation, or a generic log
grep as proof that an historical conversation recovered. Keep transient 429,
477, and upstream SSE failures separately classified from payload-schema fixes.

Use `codex-responses-proxy status --json` for current loopback diagnostics. Logs
are bounded secondary material and must not preserve request bodies, prompts,
credentials, headers, tokens, query strings, or raw upstream errors. Process
counters reset with the listener and prove neither an earlier conversation nor
a future request.

Historical context never substitutes for fresh acceptance bound to the exact
release commit.
