# Evidence Policy

Status: canonical.

A claim is accepted only with its scope, verifier, evidence, and limit stated.

- **Source evidence:** unit tests, compile checks, metadata checker, and CI.
- **Runtime evidence:** installed payload manifest, `control.py status --json`,
  verified listener identity, the secret-free loopback runtime counters, and a
  bounded reload receipt when requested.
- **User-visible evidence:** a successful response in the original failing
  conversation is distinct from transport health.

Do not treat a green local process, a new clean conversation, or a generic log
grep as proof that an historical conversation recovered. Keep transient 429,
477, and upstream SSE failures separately classified from payload-schema fixes.

The runtime counter snapshot is process-local and resets when the listener is
replaced. It contains only bounded classifications, counts, and a failure time;
it must never contain request bodies, prompts, credentials, headers, tokens, or
raw upstream errors. It is evidence of current local transport behavior, not a
claim that a particular historical Codex task has recovered.
