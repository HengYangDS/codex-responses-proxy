## 1. Portable replay contract

- [x] 1.1 Add focused tests that first fail because normal request sanitization preserves provider bindings, item IDs, reasoning/search references, and agent ciphertext.
- [x] 1.2 Add failing tests for text preservation, agent author/recipient/phase projection, function/custom-tool pairing, encrypted-only omission markers, and fail-closed unknown or malformed replay items.
- [x] 1.3 Implement the minimal portable replay normal form and run `python3.12 -m unittest tests.test_provider_portable_responses` until the RED cases are GREEN.

## 2. Provider-scoped transport

- [x] 2.1 Add failing transport tests for `/dmxapi/v1`, `/ucloud/v1`, and `/aihubmix/v1`, exact prefix stripping, query preservation, and local rejection of unknown routes.
- [x] 2.2 Implement the fixed three-route HTTPS allowlist while retaining only the bounded unscoped DMX migration route needed by protocol-v2 rollout.
- [x] 2.3 Add and pass tests proving DMX HTTP 477 fallback and cooldown never apply to UCloud/Azure or AIHubMix.

## 3. Opaque output containment

- [x] 3.1 Add failing SSE tests for reasoning, agent, and tool-output ciphertext, including encrypted-only content.
- [x] 3.2 Implement event-local atomic sanitization and omission markers without emitting partial rewrites or logging content.
- [x] 3.3 Run the focused request, transport, SSE, empty-response, and input-compatibility suites with zero failures.

## 4. Contract and release surfaces

- [x] 4.1 Update canonical runtime/authority documentation and examples with the three AIGW loopback bases, ownership boundaries, privacy rules, and migration-only route status.
- [x] 4.2 Update `VERSION` and `CHANGELOG.md` for the next patch release and keep release metadata internally consistent.
- [x] 4.3 Create the trust-bearing claim and bounded Chronicle evidence references that bind this OpenSpec change to the implementation and later acceptance receipts.

## 5. Repository proof

- [x] 5.1 Run `openspec validate provider-portable-responses --strict --json`, `python scripts/check_release_metadata.py --prepare-release`, `python scripts/check_markdown_presentation.py`, and `python scripts/test_release_metadata.py`.
- [x] 5.2 Run `PYTHON=python3.12 RUFF=ruff TY=ty sh scripts/run-python-quality.sh` and record the complete result.
- [x] 5.3 Run `for py in python3.12 python3.13 python3.14; do "$py" scripts/run-python-tests.py --compile; done` and record each interpreter's result.
- [x] 5.4 Run HEAD-bound `ethos lane status --json`, `ethos prove --execute --full --expect-head <head> --json`, and the repository release-admission checks without weakening any gate.

## 6. Successor lifecycle transfer

- [x] 6.1 Create the independently admitted `work/20260731-provider-portable-runtime-acceptance` lane from `candidate/dev` under the same holder, without modifying the predecessor source lane or application-private runtime roots.
- [x] 6.2 Transfer publication, dual-Forge proof, protocol-v2 deployment, AIGW projection, PyCharm MCP recovery, unchanged original-conversation acceptance, and final evidence closeout verbatim into the `provider-portable-runtime-acceptance` OpenSpec tasks.
- [x] 6.3 Bind claim `provider-portable-runtime-acceptance-20260731`, pass strict OpenSpec validation, and verify the successor lane reports ready before closing this source-only change.
