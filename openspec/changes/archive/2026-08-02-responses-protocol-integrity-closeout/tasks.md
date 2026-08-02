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
- [x] Transfer exact-tip GitLab and GitHub CI, signed histories, matching release
      assets, and transactional installation proof to the owner-bound
      post-archive delivery sequence without claiming those external states here.
- [x] Transfer DMXAPI, UCloud/Azure, AIHubMix, PyCharm MCP, same-original-
      conversation acceptance, and lane closeout to that delivery sequence
      without treating them as incomplete source-change tasks.

## Post-archive delivery order

These are external lifecycle and acceptance transitions. Their current truth is
established only by ETHOS, Forge, installation, runtime, client, and
repository-family evidence at execution time:

1. Land the proven source through candidate and accepted roles.
2. Publish and verify independent GitLab and GitHub histories and release assets.
3. Install only the verified release through the transactional deployment path.
4. Verify DMXAPI, UCloud/Azure, AIHubMix, PyCharm MCP, and the unchanged original
   Codex conversation without editing Codex-owned state.
5. Close the claims and retire only represented, owner-authorized lanes and
   residue.
