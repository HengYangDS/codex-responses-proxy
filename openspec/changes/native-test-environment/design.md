## Context

See [proposal.md](proposal.md). The release executable is valid on Windows, but
two black-box tests construct a replacement environment containing only `HOME`
and `PATH`. Windows requires inherited process variables before Python or the
product entry point can start.

## Goals / Non-Goals

**Goals:**

- Preserve the native host process baseline in every affected executable test.
- Keep product state and executable discovery isolated by overriding only the
  paths owned by each test.

**Non-Goals:**

- Change production process launching or lifecycle behavior.
- Add a test-environment abstraction for three local call sites.
- Relax the no-Python-on-`PATH` assertion.

## Decisions

1. **Derive each child environment directly from `os.environ`.** This preserves
   platform-defined variables without enumerating Windows, macOS, or Linux
   names. A platform allow-list would be incomplete by construction.
2. **Overlay the test-owned paths at each call site.** Three explicit mappings
   are smaller and clearer than a helper with no independent product meaning.
3. **Keep the repair in the tests.** Production already receives an ordinary
   inherited environment; changing it would widen the incident boundary.

## Risks / Trade-offs

- **A host variable could affect the executable** → product roots, home, and
  command lookup remain explicitly isolated, while the release test continues
  to exercise the exact packaged executable.
- **The test no longer starts from an empty environment** → that artificial
  condition is not a supported operating-system contract; no-Python execution
  remains covered by the isolated `PATH`.
