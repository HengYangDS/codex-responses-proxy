# Native command discoverability

## Why

The verified native payload is installed successfully, but the public
`codex-responses-proxy` command is not discoverable through the user's command
search path. Requiring an installation-directory path contradicts the product
interface and leaves `status` and `doctor` inaccessible through the documented
UX.

Installed release identity also has a duplicate, invalid reader: `status`
looks for a `VERSION` file that is not part of the installed payload instead of
using the verified installed-state record.

## What changes

- Derive one platform-native user command directory from the current user
  environment.
- Project a native symbolic link to the installed executable; do not create a
  wrapper or modify a shell profile.
- Make command projection part of the payload transaction so installation,
  upgrade, rollback, and finalization remain atomic.
- Remove the link only while it still targets this exact installed executable.
- Report release identity from the verified installed-state record and expose
  command discoverability through the existing `status` and `doctor` models.

## Non-goals

- No provider, request, Codex session, client configuration, Forge, or ETHOS
  behavior changes.
- No global installation, shell-profile mutation, alias, compatibility layer,
  or new persistent state authority.
- No assumption that a foreign command or link is product-owned.
