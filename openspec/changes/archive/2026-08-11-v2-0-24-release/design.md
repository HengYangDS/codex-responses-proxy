# Design

```mermaid
flowchart LR
    S["Accepted source"] --> V["VERSION + Changelog + README"]
    V --> Q["Local and hosted gates"]
    Q --> C["Candidate and accepted closeout"]
    C --> G["GitLab native publication"]
    C --> H["GitHub native publication"]
    G --> A["Read-only parity audit"]
    H --> A
    A --> I["Trusted installation and runtime proof"]
```

`VERSION` is the sole patch identity. Each Forge independently builds, signs,
publishes, and verifies its own tag, Release, and assets from the same accepted
tree; parity is observed only after both planes complete. The release does not
touch Codex conversation storage, JetBrains state, or provider runtime code.

The existing quality graph remains the implementation authority. This source
Change ends at accepted closeout; external delivery is neither required nor
asserted by its archive. The overall release continues immediately afterward
through the two independent Forge planes and trusted runtime acceptance.

This Change adds no compatibility path, duplicate version source, or second
publication owner.
