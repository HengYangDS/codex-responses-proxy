# Design

`.ethos/workspace.toml` is the repository declaration consumed by ETHOS. It
names roles and the single permitted local release edge; ETHOS remains the
executor, validator, and evidence owner.

```text
candidate/dev --land--> dev --accepted-to-release--> main
     local only           local exact CAS             local release root
```

GitLab and GitHub independently project the accepted source after this local
transition. Neither Forge is an input to the other or to local convergence.
