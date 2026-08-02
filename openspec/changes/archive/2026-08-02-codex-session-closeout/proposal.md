## Why

The 2.0.4 launchd projection executes `supervision/watchdog.py` by path. Its
directory then precedes the package root on `sys.path`, so the sibling
`select.py` shadows Python's standard-library `select` module and the watchdog
crash-loops before it can supervise the listener. Both streams were routed to
`/dev/null`, hiding the failure. The installed listener is currently kept alive
by a host-local emergency configuration rather than a released projection.

## What Changes

- Make direct watchdog execution package-safe and preserve macOS process argv
  identity.
- Give native supervision persistent stdout/stderr logs and create their parent
  directory before first load.
- Remove standard-library-shadowing module names from the release inventory.
- Verify private GitLab release assets through authenticated provider APIs.
- Make the locked `uv` environment the repository-owned quality boundary.
- Preserve the single configurable listener port with 8792 only as its default.

## Capabilities

### Modified Capabilities

- `runtime-upgrade`: subject=native supervision and listener configuration;
  reuse=extend; change=modify; make direct launch package-safe, preserve exact
  argv identity, persist native-service diagnostics, and retain one configurable
  listener default;
  facet:lifecycle=installation,supervision,rollback,operation;
  facet:surface=runtime,release,test,docs,openspec,evidence;
  facet:authority=source,test,docs,openspec,claim,evidence.
- `ci-diagnostics`: subject=quality environment and release-asset verification;
  reuse=extend; change=modify; pin repository-owned quality tools and authenticate
  private GitLab asset reads without weakening cross-Forge digest parity;
  facet:lifecycle=quality,ci,publication,verification;
  facet:surface=ci,tooling,release,test,docs,openspec,evidence;
  facet:authority=source,test,docs,openspec,claim,evidence.

## Out of Scope

- Editing Codex JSONL, SQLite, transcripts, archives, or model metadata.
- Modifying AIGW routes or PyCharm configuration.
- Running permanent 8791 and 8792 compatibility services in parallel.
- Retiring foreign or ownership-unknown work lanes.

## Impact

Supervision, payload projection, release verification, quality tooling,
documentation, tests, and 2.0.5 release metadata change. Publication,
installation, runtime restart, and original-task acceptance remain distinct
external transitions and require fresh evidence.
