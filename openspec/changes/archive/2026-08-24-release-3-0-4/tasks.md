## 1. Release identity

- [x] 1.1 Set `VERSION` to `3.0.4` and verify strict SemVer metadata validation.
- [x] 1.2 Add the `3.0.4` Changelog entry for the accepted publication-proof and
      host-residue corrections.

## 2. Source acceptance

- [x] 2.1 Validate the release metadata and this Change with the locked
      repository toolchain.
- [x] 2.2 Transfer exact-HEAD proof, archive, candidate integration, and
      accepted closeout to the post-archive lifecycle; require a fresh receipt
      for every effect.

## Post-archive lifecycle

Execute the exact-HEAD repository proof, archive this Change, integrate the
archived source into candidate and accepted truth, create and sign the exact
`v3.0.4` tag, build the complete native asset set, publish the identical objects
independently to GitLab and GitHub, upgrade the formal runtime transactionally,
and verify status, doctor, recover, `/healthz`, provider switching, and
continuous requests. These external effects remain incomplete until their
current receipts exist.
