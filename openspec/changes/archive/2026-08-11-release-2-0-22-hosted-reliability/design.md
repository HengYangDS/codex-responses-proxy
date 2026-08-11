# Design

## Deterministic Git fixture

Repository tests create a private branch named `fixture-root`. It cannot collide
with the product integration refs `main`, `dev`, or `candidate/dev`, so host Git
configuration no longer changes which commits the quality checker evaluates.

## Exact native-process ownership

A successful handoff deliberately leaves its successor serving. The test already
proves that PID through loopback health bound to the expected release and
payload identity. The fixture now records that PID at the proof point and
terminates it during teardown after re-reading the exact executable path and
private role. Process inventory remains a fallback for children that fail before
health is observable.

This is stricter than sleeping for a locked DLL: it closes the owned process
lifecycle before deleting the payload on every platform.
