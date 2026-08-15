## ADDED Requirements

### Requirement: Release publication uses the immutable repository runtime

GitLab release publication SHALL execute in the digest-pinned Linux release
runtime declared by repository metadata. It SHALL NOT install operating-system
packages while publishing a release.

#### Scenario: GitLab publishes a verified release

- **WHEN** the signed tag, source, quality graph, and native asset are complete
- **THEN** publication starts with Python, Git, OpenSSH, curl, binutils, and tar
  available from the immutable repository runtime
- **AND** no Debian package index or package download is required
- **AND** the publisher still executes through the locked synchronized Python
  environment.
