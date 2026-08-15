## Why

GitLab version 2.0.35 reached publication after all verification and native
asset jobs passed, but the publisher installed only quality dependencies. The
repository release command imports Cyclopts from the project runtime, so this
source state requires a forward patch identity rather than rewriting 2.0.35.

## What Changes

- Advance the sole release identity to 2.0.36.
- Record the accepted GitLab publication dependency repair.
- Publish GitLab independently without changing GitHub history, provider
  configuration, proxy protocol behavior, or the installed 2.0.35 runtime.

## Impact

Only release identity, Changelog, and this Change contract are modified. The
previous Change already contains the executable workflow repair and its full
repository proof.
