## MODIFIED Requirements

### Requirement: Platform-specific fixtures model only supported host semantics

A test fixture that depends on host shell executable-bit semantics SHALL run
only on hosts that implement those semantics, while each supported operating
system SHALL continue running its product behavior matrix. Before branch
projection creates a hosted pipeline, read-only Forge admission SHALL prove
that its required verification is schedulable. Release chronology MUST NOT
depend on unpublished workstation-only tags. Generic lifecycle fixtures SHALL
select their modeled payload platform explicitly instead of inferring payload
identity from the runner host. Windows, macOS, and Linux fixtures SHALL use the
modeled platform's path, executable-name, permission, and process semantics.
Every hosted quality target MUST report statement and branch coverage strictly
above 95%, and workflow contract checks MUST invoke the current release-asset
interface. POSIX-only shell publication harnesses SHALL not be classified as
Windows product behavior.

#### Scenario: Windows runs the supported product matrix

- **WHEN** the Windows matrix evaluates quality contracts
- **THEN** POSIX shell lookup fixtures are not treated as Windows product behavior
- **AND** all Windows product tests remain enabled.

#### Scenario: Clean hosted checkout verifies accepted source

- **WHEN** either Forge checks out the accepted branch source without local-only state
- **THEN** release metadata and governance checks complete from that source and Forge
- **AND** all scheduled platform jobs are assigned to runners and reach a terminal result
- **AND** each supported platform test matrix passes
- **AND** statement and branch coverage are each strictly above 95%.

#### Scenario: Windows executes the portable product matrix

- **WHEN** the supported test matrix runs on a Windows hosted runner
- **THEN** generic lifecycle fixtures retain their declared payload platform
- **AND** Windows-specific runtime tests explicitly select Windows semantics
- **AND** POSIX-only Forge integration harnesses are excluded without disabling
  native Windows product coverage.
