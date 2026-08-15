## 1. Release identity

- [x] 1.1 Advance `VERSION` to 2.0.35.
- [x] 1.2 Record the accepted immutable GitLab publication runtime in the Changelog.
- [x] 1.3 Preserve the failed 2.0.34 GitLab release as immutable evidence.

## 2. Verification and delivery

- [ ] 2.1 Pass release metadata, OpenSpec strict validation, and exact-HEAD proof.
- [ ] 2.2 Publish independently on GitLab and GitHub and verify all signed assets.
- [ ] 2.3 Install the trusted release and pass runtime acceptance.

## Delivery Boundary

Archive, candidate integration, accepted closeout, independent Forge
publication, trusted installation, runtime acceptance, and lane retirement are
separate lifecycle effects. Each is complete only when its own receipt proves
it.
