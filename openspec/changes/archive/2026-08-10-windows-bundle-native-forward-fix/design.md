# Design

Keep `_is_within` as the single containment owner. Normalize both operands and
the `commonpath` result so host separator rewriting cannot change identity.
The real symlink fixture remains a POSIX filesystem contract; Windows coverage
comes from native path-identity inputs and the full Windows matrix.
