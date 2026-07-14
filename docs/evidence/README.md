# Evidence Policy

Status: canonical.

A claim is accepted only with its scope, verifier, evidence, and limit stated.

- **Source evidence:** unit tests, compile checks, metadata checker, and CI.
- **Runtime evidence:** installed payload manifest, `control.py status --json`,
  verified listener identity, and a bounded reload receipt when requested.
- **User-visible evidence:** a successful response in the original failing
  conversation is distinct from transport health.

Do not treat a green local process, a new clean conversation, or a generic log
grep as proof that an historical conversation recovered. Keep transient 429,
477, and upstream SSE failures separately classified from payload-schema fixes.
