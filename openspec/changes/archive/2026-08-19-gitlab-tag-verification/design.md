## Context

`tools.forge.tag_signature` owns one provider-neutral operation: verify an exact
local product tag against an explicit external trust anchor. The GitLab workflow
retained a deleted `gitlab` positional argument from the former provider-specific
interface.

## Decision

Use the existing three-argument command directly and assert its exact shape in
the release-governance tests. GitLab and GitHub remain independent publication
peers; neither changes the signed product object.

## Consequences

The correction removes a stale compatibility token rather than adding parser
leniency. Future CLI drift fails locally before a tag is published.
