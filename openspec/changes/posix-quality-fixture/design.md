## Context

The failing fixture creates extensionless shell executables and relies on POSIX
`-x` lookup. That is not a Windows contract.

## Goals / Non-Goals

**Goals:** Scope the fixture honestly and retain the full Windows matrix.

**Non-Goals:** Change production code or weaken platform coverage.

## Decisions

Use `unittest.skipUnless(os.name == "posix", ...)` on the single fixture. The
owner remains tested on POSIX quality hosts; Windows keeps product tests.

## Risks / Trade-offs

- POSIX lookup is not re-executed on Windows -> it is not used by Windows CI.
