# Design

## Failure chain

1. A handoff successor is detached and later adopted by container PID 1.
2. Teardown sends `SIGTERM`; the process exits.
3. A non-reaping PID 1 retains the `/proc` entry in zombie state.
4. `psutil.wait()` times out because the test process is not the zombie's
   parent, while `Process.is_running()` still returns true for zombies.
5. Teardown misclassifies the exited tombstone as an orphan.

The same Linux image reproduces the decisive state: `PPID=1`, `state=Z`, no
executable and an empty command line after `SIGTERM`.

## Decision

Process ownership remains `(pid, creation time, executable)`. Observation and
termination additionally inspect the native process status. An exact-generation
zombie is terminal because it cannot execute or retain the payload. PID reuse
still fails identity comparison; unrelated error handling is unchanged.

This belongs in the process-ownership primitive rather than the fixture: every
caller receives the same portable lifecycle semantics, and the integration
assertion remains strict.
