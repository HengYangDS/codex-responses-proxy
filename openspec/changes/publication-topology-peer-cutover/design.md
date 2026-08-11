# Design

`[publication]` owns two local commands and one ordered `peers` collection.
Each peer carries its provider, role, Git remote, capabilities, and optional CI
surface. Consumers iterate that collection; no Forge-specific scalar is a
second configuration owner.

The two peers remain operationally independent. They share accepted product
semantics, not credentials, commit identities, tags, assets, jobs, or failure
state. Cross-Forge parity remains a read-only observation after both releases
exist.
