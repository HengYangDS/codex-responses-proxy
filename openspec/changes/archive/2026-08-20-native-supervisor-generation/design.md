## Context

The launchd plist names a stable installed executable path. Replacing the bytes
at that path does not replace an already-running frozen process. The prior
adapter ignored `launchctl unload` failure and then accepted `load -w` success,
so the label remained registered while the predecessor watchdog continued.

## Decision

Treat `runtime-config.json` as the only persisted product configuration used by
the installed executable. The transaction writes it with the committed payload;
the watchdog and native-service layer validate and reconstruct a minimal service
context from that carrier. Plists, systemd units, and Task Scheduler XML contain
only the executable invocation and operating-system supervision metadata. They
do not duplicate the product environment.

All platform adapters implement the same narrow operations: install the exact
service projection, query its configured executable and observed status, and
remove it. Each adapter still uses the native platform manager; no portable
supervisor framework becomes a second runtime authority.

On macOS, treat launchd service generation as an observed process identity:

1. Read the current service PID from `launchctl print gui/<uid>/<label>`.
2. If registered, boot out that exact service target and boundedly prove the old
   PID no longer exists.
3. Bootstrap the written plist into the exact GUI domain.
4. Ask launchd to start and return the service PID.
5. Re-read the service and accept only the same nonzero PID, distinct from the
   predecessor when one existed.

The listener is an independent process and remains available while the watchdog
is replaced. No signal is sent to the listener.

Service identity for an alternate installation root is derived from that exact
root. Test teardown consumes the same resolved service target and projection
path used for creation, then proves the exact label, owned processes, and
projection are absent. It never infers ownership from a name prefix or a
temporary home directory.

## Rejected Alternatives

- Legacy `unload/load`: ambiguous domain inference and ignored removal failure
  caused the incident.
- `kickstart -k` alone: replaces the process but may retain a stale cached plist.
- Path equality: an old process and new on-disk payload share the same path.
- Fixed sleeps: elapsed time does not prove process exit or launchd identity.
- A cross-platform supervisor dependency: it would hide rather than eliminate
  native service-manager semantics and add another lifecycle owner.
- Environment copies in plist, unit, or Task XML: they create parallel product
  configuration and make upgrade identity ambiguous.

## Recovery

Any invalid runtime carrier or unproved service removal, predecessor exit,
registration, start, executable identity, or successor observation fails
installation. Existing transaction rollback remains authoritative for payload
restoration. Teardown failures retain exact diagnostic state instead of silently
leaking or broadly deleting host services.
