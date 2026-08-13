## 1. Contract

- [x] 1.1 Add a failing executable contract for immutable UV/Python images, persistent UV cache, and removal of pip-based UV bootstrap.
- [x] 1.2 Prove the failure matches the observed redundant-bootstrap boundary.

## 2. Implementation

- [x] 2.1 Replace GitLab verification bootstrap with digest-pinned official UV images derived from supported Python boundaries.
- [x] 2.2 Install locked product dependencies and quality tools without a redundant editable project build, and preserve the `.python-versions` matrix owner.
- [x] 2.3 Keep GitHub, release-image ownership, runner labels, and product runtime unchanged.

## 3. Verification

- [x] 3.1 Pass focused workflow and release-metadata contracts.
- [x] 3.2 Pass quick, quality, Python 3.12/3.13/3.14, and release sessions from one frozen overlay.
- [x] 3.3 Pass the complete local gate inventory on the frozen overlay.
