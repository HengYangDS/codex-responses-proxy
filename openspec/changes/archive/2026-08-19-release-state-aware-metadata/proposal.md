# Release-State-Aware Metadata Validation

## Why

The hosted tag pipeline checks out an already tagged release. One ordinary test
still invoked the pre-tag preparation contract, so every real release tag made
the otherwise valid test suite fail.

## What Changes

- Exercise provider-neutral metadata validation through its ordinary mode.
- Preserve `--prepare-release` exclusively for the pre-tag publication window.
- Publish the correction as `2.0.46`; `2.0.45` remains immutable evidence of the
  discovered release-process defect.
