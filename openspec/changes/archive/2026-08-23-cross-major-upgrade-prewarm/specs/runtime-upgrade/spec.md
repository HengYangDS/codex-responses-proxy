## ADDED Requirements

### Requirement: Payload prewarm uses a private stable protocol

The installer SHALL prewarm the exact committed successor executable through a
private, side-effect-free executable role whose grammar is independent of the
public CLI. A public command rename or removal SHALL NOT change that protocol.
When an installed predecessor predates the stable role and cannot invoke the
successor, the operator SHALL bootstrap with the verified successor executable;
the product SHALL NOT retain a public compatibility alias solely for that
historical installer.

#### Scenario: Current installer prewarms a successor

- **WHEN** an admitted successor has been committed inside the rollback domain
- **THEN** the installer invokes the private prewarm role on that exact executable
- **AND** the role exits without reading runtime state, starting supervision, or
  changing product data.

#### Scenario: Public CLI grammar changes

- **WHEN** a release adds, renames, or removes a public command or option
- **THEN** the installer-to-successor prewarm invocation remains unchanged
- **AND** release verification fails if it is coupled to the public grammar.

#### Scenario: Historical installer lacks the stable role

- **WHEN** an installed predecessor cannot activate a breaking successor because
  it uses retired public syntax
- **THEN** the verified successor executable is used once to perform the upgrade
- **AND** no public compatibility command or permanent migration parser is added.
