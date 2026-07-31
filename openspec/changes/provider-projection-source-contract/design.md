## Context

The accepted branch and provider branch have different semantic owners. Local
`dev` is the accepted source; GitLab and GitHub independently recreate that
source DAG as signed provider-native `main` histories. Reusing one `branch`
variable for both roles accidentally required a local provider branch and made
the supported invocation impossible after a correct accepted-root closeout.

The signing runner is a lifecycle boundary, not an exception-reporting API.
Child commands already print their bounded diagnostic. Re-raising their exit as
a Python exception duplicates noise and turns an expected nonzero status into a
forbidden traceback.

## Decisions

1. `project-github-forge.sh` owns two distinct values: an explicit source ref,
   defaulting to `HEAD`, and the fixed remote target `main`.
2. The source commit and tree are frozen before the isolated clone. Every
   rewritten GitHub commit still uses the GitHub identity and trusted SSH
   signature; the push remains exact-tip leased.
3. Existing equal-name tags are checked against the frozen source commit's
   reachable tag set. No tag is copied, regenerated, or overwritten.
4. `run-provider-projection.sh` converts a failed subprocess into its original
   exit status. The child diagnostic remains on stderr; the runner adds no
   traceback or forwarding layer.
5. The offline fixture uses a canonical `dev` branch and proves that only remote
   `main` moves. A bounded runner-failure probe proves the absence of traceback.

## Risks / Trade-offs

- A caller could name a stale source ref. The script freezes and validates that
  exact ref and tree; the supported top-level invocation defaults to current
  `HEAD`, while ordinary clean-checkout and remote-tree ancestry guards remain.
- Separating source and target vocabulary adds one option. Removing the old
  overloaded `--branch` meaning is less ambiguous than retaining two meanings
  or creating a local compatibility branch.
- Preserving child stderr can expose an underlying tool diagnostic. That is the
  intended actionable output; the wrapper only removes its redundant Python
  exception rendering.

## Verification

Run the focused provider fixture and release metadata contract red then green,
the full GitHub/GitLab provider and release contracts, strict OpenSpec,
Markdown, structure, docstrings, Python 3.12-3.14, coverage above 95%, and a new
exact-HEAD ETHOS executed proof. After landing, repeat both provider projections
and inspect every exact-tip hosted job log for prohibited diagnostics.

## Rollback

Revert the source-contract commit before another projection. No provider tag,
Release, installed payload, or application-managed state is mutated by the
local failure or by the offline fixture.
