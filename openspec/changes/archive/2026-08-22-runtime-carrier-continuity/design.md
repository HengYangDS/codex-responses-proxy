## Context

The installer is the currently installed executable, not the candidate bytes.
During an upgrade, that predecessor owns admission, transaction setup, and
`runtime-config.json` serialization. A successor therefore cannot require a
carrier schema that the supported predecessor does not know how to write.

The schema change in `2.0.57` added `user_home` solely to bind macOS test and
service ownership. That value already belongs to the live `RuntimeContext` used
by installation and teardown; listener, watchdog, and handoff-child activation
do not need it.

## Goals / Non-Goals

**Goals:**

- Preserve one strict, secret-free runtime carrier across adjacent releases.
- Preserve exact macOS plist ownership through the live runtime context.
- Exercise the real predecessor executable as the upgrade controller.

**Non-Goals:**

- No schema 1/schema 2 compatibility parser or migration branch.
- No provider, endpoint, credential, handoff protocol, or timeout change.
- No mutation of the formal installed service before a verified release exists.

## Decision

Retain schema 1 as the current carrier and remove `user_home` from persisted
fields. `RuntimeContext.user_home` remains the single installation-time input
for native service creation and teardown. A reconstructed private process
context derives the current host home only where needed; product process
settings continue to come exclusively from `runtime-config.json`.

This deletes the incompatible schema expansion instead of preserving two
parsers or a migration layer. Because `2.0.57` writes the rejected schema, it
cannot be a supported predecessor for `2.0.58`; the release chain resumes from
the last usable published predecessor, `2.0.56`, and `2.0.57` is retired from
distribution after the successor is published and installed.

## Risks / Trade-offs

- [Private process reconstructs a different ambient home] -> Native service
  mutation is installer-owned and uses the explicit live context; private
  process activation does not create or remove service carriers.
- [A unit regression misses installer-generation behavior] -> The release
  compatibility gate invokes the authentic predecessor executable against the
  candidate asset before publication.
