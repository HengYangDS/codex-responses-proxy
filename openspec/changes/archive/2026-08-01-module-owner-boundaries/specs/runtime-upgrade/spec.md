## ADDED Requirements

### Requirement: Installed payload operations have concrete module owners

Each installed-payload filesystem primitive SHALL have one public module owner.
Peer modules SHALL import that owner directly and SHALL NOT recover shared
behavior through another module's private names or forwarding aliases.

#### Scenario: A payload transaction reads or writes an owned file

- **WHEN** candidate construction, migration, rollback, state, or transaction code needs a canonical payload path, safe regular-file read, digest, or atomic write
- **THEN** it calls the public owned-file module directly
- **AND** projection remains responsible only for installed projection semantics
- **AND** transaction does not re-export peer behavior as a second authority.
