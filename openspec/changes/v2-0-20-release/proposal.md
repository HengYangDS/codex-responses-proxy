# Publish v2.0.20

## Why

The accepted source contains the bounded Windows handoff cleanup that followed
the immutable v2.0.19 release attempt. A new patch release is required so both
independent Forge planes can publish that accepted tree without rewriting any
prior tag, run, or asset.

## What changes

- advance the single release identity and user-facing asset examples to
  `2.0.20`;
- preserve one shared source tree while allowing GitLab and GitHub to publish
  independently;
- require local proof, hosted CI, publication, installation, and runtime
  acceptance as distinct evidence boundaries.

## Non-goals

- no product-runtime behavior change;
- no rewrite or deletion of v2.0.19 evidence;
- no dependency from either Forge publication plane on the other.
