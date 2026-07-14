# codex-dmx-proxy v1.0.2 Hardening Design

## Purpose

Release `v1.0.2` as a bounded hardening release for the independent local
Responses compatibility proxy. It fixes replayed-image validation and Windows
service configuration propagation, then closes the release-management and
verification gaps found in the July 14, 2026 repository review.

## Scope and Boundaries

- The project remains an independent, loopback-only data-plane proxy. It is not
  merged into AIGW, which remains configuration and route control plane only.
- The proxy must never rewrite Codex session JSONL, SQLite state, or historical
  conversation metadata. It transforms only outbound `/responses` payloads.
- The release remains standard-library-only and supports Python 3.12, 3.13, and
  3.14. Its managed local service lifecycle remains macOS launchd, Linux user
  systemd/cron fallback, and Windows Task Scheduler.

## Design

### 1. Outbound replay sanitization

`input_image` entries are safe to replay only when their `image_url` is a
syntactically valid remote HTTP(S) URL: scheme `http` or `https`, non-empty
hostname, valid optional port, and no whitespace or control character. The
sanitizer removes invalid image items recursively from `content` and `output`
arrays while preserving every adjacent text/tool item and valid remote image.

This explicitly removes local paths, relative paths, Data URLs, empty-host
URLs, malformed ports, and URLs containing literal whitespace. It does not
attempt network reachability checks or DNS resolution; that would turn a
deterministic payload compatibility layer into a blocking network policy.

### 2. Windows watchdog configuration

The Scheduled Task will execute the generated `run-watchdog.cmd` through the
system command interpreter, rather than invoking `watchdog.py` directly. The
launcher owns `DMX_PROXY_PORT`, `DMX_UPSTREAM`, `DMX_PROXY_PYTHON`, and
`DMX_PROXY_SCRIPT`, so every scheduled restart receives exactly the installer
arguments. XML values are escaped before writing the UTF-16 Task Scheduler
document; command arguments use Windows-safe quotation.

### 3. Safe install/uninstall state

Installation writes a non-secret, atomically replaced state record only when it
changes a Codex `base_url`. The record names the managed config file, backup,
and loopback proxy URL. Uninstall restores a backup only if this state record is
valid and the current config still points at that recorded proxy URL. If a user
has subsequently edited the config, uninstall preserves it and explains why.

Proxy shutdown becomes port-scoped and process-identified. It must not kill all
`pythonw.exe` instances or every process whose command happens to contain the
proxy filename.

### 4. Route activation switch

The installed payload exposes a cross-platform, config-level control command:

```text
python3 ~/.codex/dmx-proxy/control.py status
python3 ~/.codex/dmx-proxy/control.py enable
python3 ~/.codex/dmx-proxy/control.py disable
```

`disable` deactivates the proxy by changing only the managed Codex route from
the recorded loopback URL back to the recorded direct upstream URL. It retains
the installed proxy and watchdog for fast, reversible reactivation; it does not
uninstall files, deregister a service, delete backups, or touch conversations.
`enable` performs the inverse config change. Both commands take a fresh backup
before a write, act only on fields recorded in the non-secret managed-state
record, and fail closed on configuration drift. `status` reports independently:
route (`enabled`, `disabled`, or `drifted`) and service (`running`, `installed`,
or `absent`).

The switch deliberately does not quit/restart a Codex Desktop application. It
reports that the application may need its normal configuration reload before a
route change becomes visible in an already-running session.

### 5. Version and release contract

`VERSION` is the release single source of truth. The installer copies it into
the deployed payload; the proxy reads it for the `Server` header. A metadata
checker verifies semantic version format, that the current changelog release
matches `VERSION`, and—when run for a tag—that the exact tag is `v<VERSION>`.

GitLab CI runs compile and unit-test checks under Python 3.12, 3.13, and 3.14,
plus the metadata checker. The release pipeline additionally enforces tag and
metadata identity. `v1.0.2` is created only after local and hosted verification
are green.

### 6. Documentation and review evidence

README, release documentation, and the original design reference use the
canonical `dig/misc/llm-third-party-api/codex-dmx-proxy` repository location.
The changelog records the user-visible behavior and limits. A review record
closes each July 14 finding with source and test evidence, while retaining known
limits: local review cannot prove Windows Task Scheduler or Linux service
behavior on physical hosts not available to this workstation.

## Acceptance Criteria

1. Invalid/local/Data image references are removed; valid remote HTTP(S) image
   references and neighboring text are preserved.
2. Windows generated Task XML launches the generated command launcher and the
   launcher carries all installer-selected proxy variables.
3. Install state is atomic and non-secret; uninstall never performs a broad
   `pythonw.exe` kill or restores a backup over a user-modified config.
4. Installed `control.py enable|disable|status` toggles only the state-recorded
   configuration route, preserves the proxy installation, and refuses drift.
5. `VERSION`, changelog release, runtime server header, Git tag, and GitLab
   release all identify `1.0.2` / `v1.0.2`.
6. Tracked CI verifies Python 3.12–3.14, package tests, compilation, and
   release metadata.
7. Local test matrix, source review, deployment payload equivalence, and an
   authenticated AIGW Codex verification all pass. Hosted pipeline status is
   inspected before release closeout.

## Non-goals

- Do not merge the proxy into AIGW or make AIGW own local service lifecycle.
- Do not provide arbitrary URL fetching, health-check URLs, or DNS reachability
  policy in the sanitizer.
- Do not normalize or mutate historical Codex conversations.
