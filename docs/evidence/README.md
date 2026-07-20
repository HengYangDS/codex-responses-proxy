# Evidence Policy

Status: canonical.

A claim is accepted only with its scope, verifier, evidence, and limit stated.

- **Source evidence:** unit tests, compile checks, metadata checker, and CI.
- **Runtime evidence:** installed payload manifest, `control.py status --json`,
  `governance.py --json`, verified listener identity, the secret-free loopback
  runtime counters including the loaded source SHA-256, and a bounded reload
  receipt when requested.
- **User-visible evidence:** a successful response in the original failing
  conversation is distinct from transport health.

Do not treat a green local process, a new clean conversation, or a generic log
grep as proof that an historical conversation recovered. Keep transient 429,
477, and upstream SSE failures separately classified from payload-schema fixes.

For operational diagnosis, prefer the loopback `control.py status --json`
snapshot and its stable counters, classifications, and failure timestamp. Logs
are bounded secondary evidence; do not archive raw logs by default, and never
use them to extract or preserve request, response, prompt, credential, header,
query, or upstream error content. A status snapshot proves only the current
listener process and cannot establish recovery of an earlier conversation.

The runtime counter snapshot is process-local and resets when the listener is
replaced. It contains only bounded classifications, counts, and a failure time;
it must never contain request bodies, prompts, credentials, headers, tokens, or
raw upstream errors. It is evidence of current local transport behavior, not a
claim that a particular historical Codex task has recovered.
