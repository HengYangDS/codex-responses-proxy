## Context

The lifecycle fixture API used `os.name` as an implicit product-platform
selector. A Windows test runner therefore changed the payload under test even
for tests that deliberately construct a Linux release asset or a platform-
neutral transaction. The Forge projection integration harness separately uses
POSIX shell executable lookup and an in-process fake command PATH.

## Decision

Generic lifecycle fixtures select the portable non-Windows payload explicitly.
Tests that model Windows continue to opt in through the existing `windows=True`
surface. POSIX Forge integration tests are skipped on Windows because they test
the shell publication harness rather than Windows runtime behavior. Hook call
recording is asserted over its complete text rather than host-specific line
splitting.

## Rejected Alternatives

- Teaching every generic lifecycle test to branch on the runner OS: this keeps
  hidden host coupling and duplicates policy.
- Adding Windows wrappers for fake Forge CLIs: this adds test-only entities to
  prove a POSIX shell surface and does not test product runtime behavior.
- Disabling the Windows matrix: this would hide real native product regressions.

## Verification

Run the previously failing lifecycle, Forge, and governance tests, then the
full supported Python matrix and quality gates. Hosted GitHub Windows jobs and
both Forge branch pipelines must reach successful terminal states.
