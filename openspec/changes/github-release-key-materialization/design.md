# Design

GitHub owns conversion from its text-secret representation to the product's
existing file-path contract. Product signing receives only the path.

| Boundary | Owner |
| --- | --- |
| Text secret | GitHub Actions |
| Mode and terminal newline | GitHub workflow adapter |
| OpenSSH signing and verification | Release tooling |
| Concise error rendering | Release CLI boundary |
