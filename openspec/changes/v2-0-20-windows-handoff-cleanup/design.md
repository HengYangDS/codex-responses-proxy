# Design

The fixture already proves every process naming its copied executable has
exited before deleting the payload. Preserve that authority boundary. Wrap only
the final `TemporaryDirectory.cleanup()` in a bounded retry for
`PermissionError`, because Windows may release mapped modules asynchronously.
All other errors remain immediate failures, and a persistent lock still fails
when the deadline expires.
