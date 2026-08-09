## Why

GitLab jobs currently select mutable Python minor image tags. A later registry
update can therefore change the build environment without any repository diff.

## What Changes

- Bind the supported floor and latest Python images to supported minor tags and immutable registry digests.
- Validate the image contract against `.python-versions` without copying version
  values into tests.

## Boundary

This Change only strengthens reproducibility of the GitLab execution plane. It
does not couple GitLab to GitHub, add a package-version owner, or change product
runtime behavior.
