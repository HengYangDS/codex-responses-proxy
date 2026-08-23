## 1. Reproduce and repair

- [x] 1.1 Add a failing regression that requires candidate prewarm to use one
  private runtime role rather than public CLI syntax.
- [x] 1.2 Add the side-effect-free private role and switch the transaction probe
  to it without adding a compatibility alias.
- [x] 1.3 Add application-level coverage proving the role bypasses runtime
  activation and remains outside the public command grammar.
- [x] 1.4 Delete the unreachable renderer branch for the retired public
  `version` command.

## 2. Validate and deliver

- [x] 2.1 Run focused lifecycle and CLI tests plus strict OpenSpec validation.
- [x] 2.2 Update operator documentation and release history with the explicit
  historical bootstrap boundary.
- [x] 2.3 Run the complete quality, Python compatibility, native release, and
  authentic predecessor compatibility gates.
- [x] 2.4 Archive the completed Change after its surviving runtime-upgrade
  contract is absorbed into the canonical specification.
