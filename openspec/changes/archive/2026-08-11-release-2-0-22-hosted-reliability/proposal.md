# Restore hosted release reliability

## Why

The public v2.0.21 attempt exposed two host-dependent test defects. The Git
fixture inherited the machine's default branch name, and native handoff tests
did not retain the exact successor PID that kept a Windows bundle mapped.
Neither defect belongs in production routing or provider behavior.

## What changes

- initialize isolated Git fixtures on one non-product branch;
- retain and terminate each successor PID observed through authenticated health;
- keep process discovery as a secondary exact-path safety net;
- advance the forward-only patch release to 2.0.22 after complete proof.

## Non-goals

- no retry-only workaround or longer Windows cleanup delay;
- no change to provider, replay, backpressure, or handoff protocol semantics;
- no rewrite of v2.0.20 or v2.0.21 tags, runs, Releases, or assets.
