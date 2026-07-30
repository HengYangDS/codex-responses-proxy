# Design

Recovery observes two valid identities at once: the old code still serving in
memory and the candidate payload already committed on disk. Treating them as
one projection makes the contract contradictory. The verifier therefore
derives the runtime fields from the rollback snapshot and only the manifest
digest from the committed candidate. Both projections remain fully verified
before rollback mutates disk.
