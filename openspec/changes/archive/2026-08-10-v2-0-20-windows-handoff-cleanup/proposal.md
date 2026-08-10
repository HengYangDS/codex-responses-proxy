# Windows Handoff Cleanup Forward Fix

## Why

v2.0.19 fixed bundle containment, but its real Windows release gate exposed a
separate teardown race: the OS can retain a mapped native module briefly after
all fixture-owned proxy processes exit. Immediate temporary-directory removal
then fails with `WinError 5`.

## What changes

- keep process termination and exact identity checks unchanged;
- retry only transient payload cleanup until a short deadline;
- hand the proven fix to a separate release-preparation change so v2.0.20 can
  update every user-facing release reference without widening this repair.
