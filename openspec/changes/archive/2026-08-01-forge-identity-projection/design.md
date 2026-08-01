## Context

GitLab owns the canonical source commit history. GitHub owns a separate verified
identity domain. Git commit identity and signature are object content, so the two
Forge tips cannot share an OID when their required emails differ. Source content,
messages, dates, and merge topology can nevertheless remain equivalent.

## Decisions

1. One direct `tools/forge/project.sh` command selects `gitlab` or `github`;
   provider-specific wrappers are deleted.
2. The external publication context owns actor name, actor email, and active SSH
   fingerprint for each Forge. Product source contains no personal default.
3. GitLab accepts only canonical commits with its configured email and trust.
4. GitHub maps an existing verified tip to exactly one canonical commit using an
   identity-neutral fingerprint of tree, parent count, dates, and message. Only
   later canonical commits are recreated with the GitHub identity and signature.
5. Ordinary non-force push is the concurrency and no-rewrite guard.
6. A JSON mapping receipt records source commit, projected commit, tree, base,
   and newly created pairs. The receipt is caller-owned operational evidence.
7. Parity means distinct provider commits, equal tip tree, equal ordered tree
   history, correct provider emails, valid signatures, and equal release assets.

## Risks / Trade-offs

- Historical histories lacking a unique identity-neutral match fail closed and
  require an explicitly recorded migration rather than an automated guess.
- Commit OIDs intentionally differ, so tooling that assumed object equality must
  consume tree-history parity or the explicit mapping receipt.

## Verification

Run the offline projection tests red then green, parity-audit tests, release
metadata and tagging contracts, strict OpenSpec, Markdown, Python 3.12-3.14,
statement and branch coverage above 95%, and exact-HEAD ETHOS proof.

## Rollback

Revert the source change before either remote projection. The offline tests use
temporary remotes and do not mutate hosted refs, tags, Releases, or runtimes.
