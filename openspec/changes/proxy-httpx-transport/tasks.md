## 1. Falsify the Assumption

- [x] 1.1 Run a focused HTTPX 0.28.1 loopback probe that changes the active stream read timeout from 2.0 seconds to 0.1 seconds after the first chunk; verify the second read still blocks until the delayed server response.
- [x] 1.2 Compare the failed public-timeout contract with the current total SSE deadline and reject private HTTPCore access, reader-thread cancellation, and an asynchronous rewrite as net complexity increases.

## 2. Correct the Durable Decision

- [x] 2.1 Amend DR-0006 to remove the unsupported HTTPX selection and state the evidence-based replacement bar; verify the decision register still links one authoritative record.
- [x] 2.2 Verify `pyproject.toml`, `uv.lock`, and runtime source contain no HTTPX dependency, adapter, fallback, or parallel upstream path.

## 3. Acceptance

- [x] 3.1 Run documentation format, link, and governance checks; verify the accepted runtime and product code remain unchanged.
- [x] 3.2 Re-run OpenSpec strict validation, mark current evidence complete, and archive this no-behavior Change.
