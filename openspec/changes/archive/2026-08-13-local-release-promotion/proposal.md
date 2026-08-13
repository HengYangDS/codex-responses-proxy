# Local Release Promotion

## Why

The repository already specifies ETHOS closeout as the sole authority that
advances local release `main` from accepted `dev`. A second Proxy-owned command
would duplicate that transition, widen the product surface, and couple product
code to repository governance.

## What Changes

- Keep `ethos land --closeout` as the only local release-root transition.
- Demonstrate that the transition is local-first, exact-head guarded, and
  independent of GitLab and GitHub.
- Add no Proxy runtime, Forge, wrapper, or compatibility command.

## Non-goals

- Remote publication, tag or Release mutation.
- Client configuration or Codex session mutation.
- A second release-root state machine in Proxy source.
