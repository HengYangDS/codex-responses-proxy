## Context

The accepted source now synchronizes both the locked project and quality group
before GitLab invokes repository release tools. GitHub publication remains an
independent plane and already published 2.0.35 successfully.

## Decisions

`VERSION` advances to 2.0.36. Reusing 2.0.35 would conflate the failed GitLab
publication source with its forward repair. No second version carrier,
compatibility path, provider change, or runtime behavior change is introduced.

## Delivery Boundary

Local proof, archive, candidate integration, accepted closeout, GitLab tag and
Release creation, asset verification, installation, and runtime acceptance are
distinct effects. This Change records only facts proven at each stage.
