# Windows successor ownership

## Problem

The handoff protocol proves the successor PID and complete serving identity, but
test cleanup tries to prove that same process again from `cmdline()[0]`.
Windows may project a bundled executable through a launcher path that is not the
installed path, so the second proof rejects a valid successor and leaves its
native modules mapped.

## Change

Capture the already-proven successor as an exact PID generation using its
creation time. Keep argv verification for process discovery; do not require it
after protocol health has already established ownership.

## Outcome

Native handoff tests terminate the exact observed generation before deleting
the temporary payload. PID reuse and foreign processes remain fail-closed.
