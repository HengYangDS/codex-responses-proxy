## 1. Correct acceptance semantics

- [x] 1.1 Replace the redundant raw listener-PID poll with the existing full
      runtime-identity comparison between upgrade output and product status.
- [x] 1.2 Verify the test remains collected and focused quality and Forge
      contract tests pass without warnings.

## 2. Source closeout

- [x] 2.1 Pass strict OpenSpec validation and archive this completed source
      change before updating the published proposal commit.

## Post-archive lifecycle

Verify the Windows published-predecessor compatibility job on the exact updated
proposal commit. After all required GitHub and GitLab checks pass, merge that
commit without rewriting it and remove both proposal branches. These hosted
effects remain incomplete until current Forge receipts exist.
