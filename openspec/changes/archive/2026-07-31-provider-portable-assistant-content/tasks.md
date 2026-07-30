## 1. Incident contract

- [x] 1.1 Bind the v1.0.43 original-thread failure to the exact assistant
  `input_text` validation error, installed runtime identity, route, and unchanged
  session-prefix evidence.
- [x] 1.2 Validate the proposal, design, delta specification, scope, and
  ownership boundary before implementation writes.

## 2. TDD regression

- [x] 2.1 Change focused request tests to require assistant and synthesized
  agent visible text, refusal text, and omission markers on the assistant Easy
  Input Message string carrier, while system/developer/user text remains
  `input_text`.
- [x] 2.2 Run the focused provider-portable and policy tests and record the
  expected RED failure against the unchanged production projector.
- [x] 2.3 Change classified-empty-response projection and transport tests to
  require the same assistant string and input-content grammar, including
  replayable remote images, then record the expected RED failure against the
  unchanged fallback projector.

## 3. Minimal implementation

- [x] 3.1 Make both normal and classified-empty-response projection emit
  textual assistant and synthesized-agent history as assistant strings while
  leaving system/developer/user and function/custom-tool output on validated
  input-content grammar.
- [x] 3.2 Run the focused request, policy, transport, input, and empty-response
  suites until the new regression and all existing contracts are GREEN.

## 4. Release and evidence surfaces

- [x] 4.1 Update the canonical capability spec, VERSION, and CHANGELOG for
  v1.0.44 without claiming publication or installation.
- [x] 4.2 Create the bounded claim and Chronicle record for the source fix,
  including the failed v1.0.43 acceptance boundary and the no-session-write
  invariant.

## 5. Complete local proof

- [x] 5.1 Run strict OpenSpec validation, release metadata, Markdown
  presentation, and release-contract tests.
- [x] 5.2 Run `PYTHON=python3.12 RUFF=ruff TY=ty sh
  scripts/run-python-quality.sh` and retain the complete result.
- [x] 5.3 Run the compile-and-behavior matrix on Python 3.12, 3.13, and 3.14.
- [x] 5.4 Run HEAD-bound lane status and full executed ETHOS proof with no
  weakened gate.

## 6. Successor transfer and source closeout

- [x] 6.1 Transfer v1.0.44 dual-Forge publication, protocol-v2 deployment, and
  resumed unchanged-original-thread acceptance into the existing
  `provider-portable-runtime-acceptance` OpenSpec authority.
- [x] 6.2 Archive this source change only after every source task passes and
  leave publication, deployment, and runtime completion unclaimed; governed
  landing follows through ETHOS after the archived source commit is signed.
