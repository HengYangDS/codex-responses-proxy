# Design

Apply os.path.normcase and os.path.commonpath to already resolved paths. Path
resolution still removes symlink indirection; the host owns case semantics.
Traversal, cycle detection, regular-file checks, deterministic inventory,
manifest, and signatures are unchanged.
