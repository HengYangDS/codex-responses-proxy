# Design

`VERSION` already owns release identity for packaging and metadata. The
canonical requirement now refers to the exact value read from that file instead
of copying a concrete patch number into policy prose.

This keeps one semantic owner and lets GitLab and GitHub project the same source
identity independently. Historical release evidence remains immutable and is
not part of the current release contract.
