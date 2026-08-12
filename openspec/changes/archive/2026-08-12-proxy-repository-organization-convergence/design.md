## Decision

Retain `uv + nox + hatchling` as the single Python development and packaging stack. Keep the native executable as the only operator-facing product surface. Existing `VERSION` remains the sole release authority.

ETHOS owns branch lifecycle; Proxy owns wire compatibility, provider registry, release payload, and native supervision. AIGW owns client configuration and never becomes a Proxy dependency. GitLab and GitHub publish independently from local-first accepted source.

## Ownership

| Concern | Owner |
|---|---|
| Release version | `VERSION` |
| Package metadata | `pyproject.toml` |
| Quality graph | `noxfile.py` and locked `uv` environment |
| Branch transition | ETHOS public command |
| Provider behavior | `src/codex_responses_proxy/providers` |
| Runtime lifecycle | `src/codex_responses_proxy/lifecycle` |
| Forge publication | provider-native workflows |

## Rejected

- a second version file or compatibility reader;
- exposing `python -m` as product UX;
- shell-specific installer contract;
- coupling to AIGW, Workstation, JetBrains, or Codex session storage.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `repository-organization:One release identity` | `1.1` | `focused-tests` |
| `repository-organization:Governed release-branch convergence` | `2.1` | `ethos-closeout-receipt` |
| `repository-organization:Portable product and repository UX` | `3.1` | `repository-quality-gate` |
