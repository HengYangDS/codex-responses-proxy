## Why

A verified `2.0.52` upgrade replaced the listener and payload but left the
resident launchd watchdog PID unchanged. The macOS adapter ignored failure from
the legacy unload command and treated a successful load as supervision
convergence, even though the old process continued executing predecessor frozen
bytes.

## What Changes

- Make `runtime-config.json` the sole secret-free carrier from which the product,
  watchdog, and native-service adapters reconstruct runtime identity.
- Keep platform service definitions as derived projections rather than parallel
  product configuration.
- Replace legacy `launchctl unload/load` with exact GUI-domain generation
  replacement and prove predecessor exit plus successor identity.
- Bind launchd, systemd user services, and Task Scheduler to one narrow native
  supervision contract while retaining their platform-native registration.
- Make isolated lifecycle teardown prove exact service, process, and projection
  removal without changing the canonical listener or service.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-upgrade`: native supervision derives from one runtime carrier;
  macOS additionally proves resident process-generation replacement rather
  than plist registration alone.

## Impact

Runtime carrier ownership, native supervisor adapters, lifecycle test resource
ownership, release identity, and the runtime-upgrade contract change. Provider
routing, handoff wire behavior, credentials, and client configuration remain
unchanged.
