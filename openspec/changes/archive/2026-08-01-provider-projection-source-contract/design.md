## Context

The terminal product is a provider-neutral local compatibility proxy for the
OpenAI Responses protocol. Provider names belong to route/profile adapters and
provider-specific compatibility policies, not to the product identity. Current
history and release records remain immutable, while all current authority
surfaces migrate to `codex-responses-proxy` without a permanent alias layer.

The accepted branch and Forge publication targets have different semantic owners,
while the collaborative commit graph has one immutable author and signature history.
Local `dev` is accepted source; Forge `main` refs are forward-only projections of
that same graph. Expected child failures preserve their bounded diagnostic and exit
status without an added Python exception traceback.

Signing authority enters only through explicit external context and the standard
OpenSSH agent protocol. The repository never owns passwords, agent setup, private
key paths, or maintainer-specific workstation state.

## Decisions

1. The canonical product identity is **Codex Responses Proxy**; repository slug,
   Python package, environment namespace, installation root, service identifiers,
   current docs, tests, and release metadata use that identity.
2. DMXAPI, AIHubMix, and UCloud remain explicit provider profiles in the one
   released manifest. An ordinary provider adds only one manifest table. Only
   genuinely provider-specific protocol behavior may retain a provider name;
   it adds one semantic policy module and one manifest declaration, while the
   registry and release inventory remain provider-neutral.
3. The migration is one-way. Historical Git objects, releases, and evidence keep
   their truthful old names; executable compatibility shims and duplicate runtime
   namespaces are not retained.
4. Third-party Responses transport is stateless across turns. The proxy sets
   `store=false` before the first network attempt and preserves it in every
   bounded recovery. Portable dialogue and complete tool relationships carry
   continuity; no provider-issued response, item, or conversation identity
   crosses the boundary.
5. Forge tag identity and signing fingerprint are explicit publication inputs.
   Product scripts contain no maintainer identity, key filename, home-directory
   assumption, Keychain integration, agent creation, or retry bridge.
6. Tag commands select the exact public key from the caller's existing OpenSSH
   agent and use standard `ssh-keygen`; missing capability exits immediately.
7. Both Forge publishers consume the same clean, signed accepted source and only
   fast-forward the target branch.
8. Commit authorship and signatures remain immutable collaboration evidence;
   Forge automation never recreates the DAG.
9. Existing tags and Releases are immutable history. A new release uses one exact
   source tree and independently verified Forge-native tag and Release records.
10. Both Forges publish the same deterministic `tar.gz` built from immutable
    `HEAD` blobs plus one `SHA256SUMS`. Publication proof downloads the assets,
    validates the manifest, and compares both complete digest maps.
11. Provider and release commands are direct semantic entrypoints under `tools/`;
    retired forwarding layers are deleted.
12. Current source, tests, docs, OpenSpec, CI, release, and deployment surfaces use
    the provider-neutral product identity. Historical carriers remain truthful.

## Risks / Trade-offs

- A Forge may diverge from accepted source. Publication fails closed rather than
  rewriting or force-updating history.
- Existing installations and historical records use the former identity. Runtime
  migration is transactional and evidence-bound; source keeps no permanent alias.
- Provider-neutrality can be undermined by hidden defaults. The repository gate
  therefore rejects implicit unscoped routes, retired source roots, personal paths,
  and duplicate provider registries.

## Verification

Run the focused provider fixture and release metadata contract red then green,
the full GitHub/GitLab provider and release contracts, strict OpenSpec,
Markdown, structure, docstrings, Python 3.12-3.14, coverage above 95%, and a new
exact-HEAD ETHOS executed proof. Release contract tests additionally rebuild the
archive, exercise both Forge upload/download paths, and require digest equality.
After landing, repeat both provider projections and inspect every exact-tip
hosted job log for prohibited diagnostics.

## Rollback

Revert the source-contract commit before another projection. No provider tag,
Release, installed payload, or application-managed state is mutated by the
local failure or by the offline fixture.
