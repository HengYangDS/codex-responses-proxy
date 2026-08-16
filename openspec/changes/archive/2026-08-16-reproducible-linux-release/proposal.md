# Reproducible Release and Reliable Handoff

## Why

Release 2.0.38 proved equivalent source trees on GitLab and GitHub but produced
different Linux executable hashes. The only differing PyInstaller member was
the Python 3.14 `ctypes` bytecode archive, whose reconstructed code objects had
equal semantics but different marshal reference identities.

The same release also exposed an independent upgrade defect: the installer
allowed only ten seconds for the current listener to return `READY`, while a
cold final macOS executable can need longer even though it remains within the
operator's configured installation deadline.

## What Changes

- Use PyInstaller's supported hook mechanism to collect `ctypes` as source
  outside the nondeterministic bytecode archive.
- Prewarm the exact executable inode committed to the installation, not a
  temporary copy that cannot warm the successor.
- Give the `READY` exchange the configured bounded deadline plus a small
  transport margin; remove the independent ten-second cap.
- Release the forward fix as 2.0.39 without rewriting 2.0.38.

## Non-goals

- Rewriting PyInstaller archives or vendoring standard-library code.
- Weakening release admission, rollback, listener identity, or transaction
  recovery.
- Changing provider routing, client configuration, or Codex session state.
