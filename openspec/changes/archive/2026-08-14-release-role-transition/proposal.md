# Declare the local release transition

## Why

The accepted specification assigns local `dev` to `main` convergence to ETHOS,
but the repository does not declare that transition in its machine-readable
branch-role policy. ETHOS therefore cannot execute the contract it owns.

## What changes

- Declare the repository's five branch roles.
- Admit one `accepted-to-release` transition from `dev` to `main`.
- Require exact executed proof before that transition.
- Keep both Forge publication planes outside the local transition.

## Non-goals

- No Proxy-owned Git mutation command.
- No remote push, tag, Release, asset, installation, or runtime change.
- No compatibility path or second branch-policy owner.
