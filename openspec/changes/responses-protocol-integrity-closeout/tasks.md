# Tasks

- [x] Add RED tests for non-stream JSON ciphertext removal.
- [x] Add RED tests for empty, incomplete, malformed, and incomplete-status
      successful Responses bodies.
- [x] Add RED tests for empty Responses request rejection before upstream I/O.
- [x] Add RED tests for ambiguous provider route suffixes.
- [x] Implement one provider-neutral JSON/SSE response projection owner.
- [x] Buffer and validate successful non-stream Responses before commitment.
- [x] Close empty-request and route grammar admission gaps.
- [x] Replace the provider-specific empty-response interface with the optional
      provider-neutral wire-policy contract and structured failure classifiers.
- [x] Add RED tests that require one-call HTTP 429 relay, no proxy sleep,
      provider-scoped cooldown, bounded `Retry-After`, route isolation, and a
      conservative configurable concurrency default.
- [x] Implement and prove the complete provider-backpressure contract without a
      provider-name branch or Codex-state mutation.
- [x] Align README, architecture, docstrings, comments, Changelog, and the
      canonical capability specification with the proven replay subset.
- [x] Align README, architecture, docstrings, comments, and Changelog with the
      implemented backpressure contract and the prepared release metadata.
- [x] Run focused protocol and backpressure tests on Python 3.12, 3.13, and 3.14.
- [x] Run Ruff, ty, repository architecture, statement coverage, and branch
      coverage gates above 95%.
- [x] Validate all OpenSpec changes strictly and verify no Codex-owned data was
      modified.
- [ ] Obtain exact-tip green GitLab and GitHub CI, signed histories, matching
      release assets, and formal transactional installation evidence.
- [ ] Verify DMXAPI, UCloud/Azure, AIHubMix, PyCharm MCP calls, and the same
      original Codex conversation, then close every owned lane and residue.
