## Context

`scripts/run-python-quality.sh` now resolves the requested Ruff and ty versions
semantically. `scripts/test_release_metadata.py` still asserted the deleted
case-pattern text, so GitLab rejected an otherwise passing tag pipeline. Debian
also emitted debconf fallback warnings because package installation did not
declare its noninteractive frontend.

## Goals / Non-Goals

**Goals:**

- Pin public behavior and version policy without coupling tests to shell syntax.
- Make hosted dependency bootstrap intentionally noninteractive and quiet.
- Preserve immutable provider-native tag and Release history.

**Non-Goals:**

- Rewriting `v1.0.37`, weakening release gates, or changing runtime semantics.
- Editing Codex session state or AIGW-owned configuration.

## Decisions

1. The regression test executes the owner with controlled fake tools and checks
   that it skips an earlier wrong version in `PATH`. This proves the behavior
   that failed previously without prescribing implementation text.
2. Tool versions remain explicit constants in the owner and CI projections;
   tests assert those stable policy values separately.
3. GitLab sets `DEBIAN_FRONTEND=noninteractive` at pipeline scope and uses quiet
   apt flags in the shared command spelling. Provider files remain thin; no
   product logic moves into YAML.
4. The repair uses a new patch release. Existing signed tags and failed hosted
   executions remain immutable observations.

## Risks / Trade-offs

- A fake-tool regression can drift from real executables -> retain the existing
  hosted quality job and exact version checks as the integration proof.
- Quiet apt output can hide progress -> errors still surface and exit nonzero;
  only routine chatter and frontend fallback warnings are suppressed.
