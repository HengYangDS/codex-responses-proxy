## ADDED Requirements

### Requirement: Hosted native asset jobs preserve path identity

A hosted native asset job SHALL write each accepted platform bundle to the exact directory consumed by its artifact uploader across every process, container, and host boundary.

#### Scenario: Linux build runs in a job container

- **WHEN** the pinned Linux release container builds and accepts the native asset
- **THEN** the output directory is mounted into both the container and host action
- **AND** the upload action reads that exact directory without path translation
- **AND** GitLab and GitHub continue to build and publish independently
