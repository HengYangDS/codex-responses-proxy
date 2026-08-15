# Design

The ordinary projector still resolves the current provider tip by an
identity-neutral canonical match. The recovery path is deliberately explicit:
the caller supplies a canonical ancestor, the provider commit that represents
that ancestor, and the exact provider tip observed before mutation.

The projector verifies the complete existing provider history against the
selected identity and trust anchor. It then proves the canonical base has one
identity-neutral provider match, compares that match with the supplied
projected anchor, and compares the live tip with the supplied expected tip. The
live tip becomes the projected parent for the canonical base, so only canonical
successors are recreated. The final push remains atomic and non-forced.

The read-only parity audit treats the equal ordered suffix ending at both
current tips as the semantic lineage shared by the two independent provider
histories. Earlier provider prefixes may differ because each plane can have a
different historical cutover, but the current tip tree and non-empty shared
suffix must agree.
