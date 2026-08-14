# Terminal convergence

## Why

The accepted product already carries the core provider-portable Responses and
native lifecycle design, but several historical Work Lanes still contain
unresolved or duplicated release, rollback, portability, and quality intent.
Keeping those lanes alive creates competing authority and prevents a bounded
product closeout.

## What changes

- Audit every remaining Work Lane against current `dev`, absorb only unique
  product behavior, and retire or discard superseded carriers.
- Preserve stateless provider switching: requests use `store=false`, replay
  state is provider-portable, empty upstream responses recover without leaking
  transport artifacts, and backpressure remains provider-scoped.
- Complete native upgrade rollback so candidate-only files are removed while
  prior and unknown content remain exact.
- Converge repository structure, documentation, quality policy, independent
  Forge delivery, signed assets, installation, and runtime acceptance around
  one proved source revision.

## Non-goals

- No Codex transcript, JSONL, SQLite, history, or model-metadata mutation.
- No client configuration, Workstation, ETHOS, JetBrains, or PyCharm authority.
- No compatibility shell, forwarding facade, Forge dependency, or
  provider-specific product fork.
