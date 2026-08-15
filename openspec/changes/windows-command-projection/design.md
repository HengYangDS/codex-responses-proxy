# Design

## Semantic Owner

`lifecycle.command` remains the sole owner of command-path projection and
classification. Its existing platform split is retained: `os.symlink` on
POSIX, `os.link` on Windows, followed by the same `os.path.samefile` ownership
proof.

## Verification Boundary

Tests assert the common contract first: the command path is a regular,
product-owned projection of the installed executable. POSIX tests additionally
prove symbolic-link identity; Windows tests prove hard-link identity. Failure
injection patches the native primitive selected by the running platform.

CLI status fixtures construct host-native absolute paths. Production path
validation remains strict; the test no longer asks Windows to accept a POSIX
path as native installed state.

## Rollback

Rollback continues to store device and inode evidence, replace only an absent
or exactly owned path, and recreate the platform-native projection after the
prior payload is restored. No second state or compatibility reader is added.
