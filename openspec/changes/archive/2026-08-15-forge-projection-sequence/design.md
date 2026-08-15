# Design

The explicit base is already proven to have one unique identity-neutral match.
It therefore defines a deterministic position in each ordered history. Prefix
commits before those positions belong to earlier publication epochs and are not
candidate mappings for canonical successors.

The mapper slices both ordered indexes immediately after the exact base and
anchor. It maps equal successor fingerprints only within those suffixes. More
than one provider successor with the same fingerprint remains ambiguous and
fails before commit creation or ref mutation.

Automatic mode retains its complete-history contract. Provider identity and
signature checks retain their existing exact anchor-to-tip boundary, and the
push remains atomic and non-forced.
