## 1. Release identity

- [x] 1.1 Advance `VERSION` to 3.1.12 and record the accepted protocol and quality fixes in `CHANGELOG.md`; verify release metadata validation passes.

## 2. Product evidence

- [x] 2.1 Run strict source, quality, and supported Python gates from the locked environment and verify no warning or failure.
- [x] 2.2 Build the current-platform source-independent asset and verify isolated install, replay projection, recovery, health, and exact uninstall without changing the canonical service.
- [x] 2.3 Verify strict OpenSpec validation and archive readiness on the complete source Change.

## Post-archive lifecycle

After source acceptance, archive this Change and integrate the archived source
into candidate and accepted truth. Then create the signed `v3.1.12` tag, build
the complete native inventory, publish byte-identical objects and assets to
GitLab and GitHub, and verify each Forge independently. Upgrade the canonical
installation transactionally only from the verified release, then prove health,
replay behavior, rollback authority, and residue-free Work Lane retirement.
These external effects require fresh evidence and are not OpenSpec completion
checkboxes.
