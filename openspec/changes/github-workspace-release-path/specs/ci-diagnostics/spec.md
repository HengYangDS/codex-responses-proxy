# CI diagnostics delta

## ADDED Requirements

### Requirement: Container and action paths share one mounted workspace

The GitHub Linux release job SHALL write its output through the container's
runtime `GITHUB_WORKSPACE` path. The upload action SHALL read the equivalent
`${{ github.workspace }}` path.

#### Scenario: Linux native asset crosses the container boundary

- **WHEN** the tagged Linux job builds the native release asset
- **THEN** the container writes below `$GITHUB_WORKSPACE/.release-assets`
- **AND** the upload action reads `${{ github.workspace }}/.release-assets`
