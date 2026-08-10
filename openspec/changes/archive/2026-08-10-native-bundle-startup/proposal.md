# Use one prewarmed native bundle

## Why

The current PyInstaller one-file payload extracts and re-enters operating-system
inspection on every process start. Native handoff tests exceed their bounded
startup window, and the same repeated work degrades real reloads. Increasing the
timeout would preserve the defect.

## What changes

- Build one PyInstaller directory bundle and remove the one-file build path.
- Package every bundle file in the signed platform archive and manifest.
- Install and verify the complete inventory as one transactional payload.
- Prewarm the staged executable before it can replace the current payload.
- Keep startup, handoff, rollback, purge, and recovery bound to the same manifest.

## Non-goals

- No alternate freezer, compatibility archive, legacy payload reader, or timeout
  increase.
- No provider, protocol, client configuration, Forge, or release-signing change.
