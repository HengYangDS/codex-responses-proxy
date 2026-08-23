## Context

The installer is the currently running release. During commit it replaces the
payload and then starts the successor executable as a prewarm probe. Release
2.0.58 encoded that probe as the public `version` subcommand; release 3.0.0
removed that redundant command in favor of `--version`, so the old installer
rolled back a valid successor. The transaction and rollback behavior worked,
but the cross-generation protocol was owned by public presentation syntax.

## Goals / Non-Goals

**Goals:**

- Give prewarm one private, stable, side-effect-free executable role.
- Keep the probe inside the existing transaction and exact-executable boundary.
- Prove that public version syntax is no longer a lifecycle dependency.
- State the one-time bootstrap boundary for predecessors that already shipped
  with incompatible syntax.

**Non-Goals:**

- Restore the removed public `version` command.
- Add a version-specific parser, shim, launcher, or second installer.
- Change handoff, service supervision, provider routing, or release admission.

## Decisions

### Use one private executable role

`service.runtime` owns the private role name because it already owns listener,
watchdog, and handoff-child process roles. The application dispatches prewarm
before runtime activation and exits successfully. Reaching that dispatch proves
the frozen executable can materialize and import its command plane; it does not
need runtime configuration or service state.

This is preferable to probing `--version`, `--help`, or another public command:
those are user interfaces and may change deliberately. It is also preferable to
an extra probe executable or file because the transaction must test the exact
binary that will become the service payload.

### Do not disguise the already-broken 2.x boundary

No 3.x source change can alter the command issued by an already installed 2.0.58
binary. Preserving `version` would make the public grammar parallel again. The
bounded migration is therefore explicit bootstrap with the admitted successor
executable; after that transition, installers use the stable private role.

## Risks / Trade-offs

- [The private role is accidentally exposed as public CLI] -> Keep it outside
  the Cyclopts command registry and cover public help plus unknown-command tests.
- [The role acquires side effects] -> Test that it returns before runtime
  activation and keep its implementation as a direct zero result.
- [A future refactor renames the role] -> Bind installer and candidate tests to
  the one constant owned by `service.runtime`.

## Migration Plan

1. Release the successor with the stable private role and installer invocation.
2. Existing 3.0.0 installations upgrade normally and establish the new protocol.
3. A remaining 2.x installation invokes the verified successor executable once;
   no historical command alias remains afterward.
4. Rollback continues to use the existing exact predecessor snapshot whenever
   successor prewarm fails.
