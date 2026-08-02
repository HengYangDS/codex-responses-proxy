## Context

launchd invokes the watchdog by absolute script path. Before Python can execute
the watchdog's package bootstrap, `subprocess` imports `select`; the sibling
`supervision/select.py` wins resolution and imports the unavailable package.
The watchdog exits before writing an application log, while the plist discards
both standard streams. Separately, a Python process launched through the macOS
framework executable must retain the script/module argv used by ownership
checks.

## Decisions

### 1. Bootstrap before imports that can resolve sibling modules

The watchdog removes its script directory from `sys.path` and inserts the
package root before importing `subprocess` or package modules. A subprocess
regression test loads the file from an unrelated current directory.

### 2. Eliminate shadowing names rather than retain shims

`supervision/select.py` becomes `native_service.py` and `runtime/logging.py`
becomes `operational_log.py`. All imports and exact payload inventories follow
the semantic owner. No compatibility wrappers remain.

### 3. Native service failure is observable from first install

The plist writes stdout and stderr below the application log directory, and the
installer creates that directory before loading launchd. Tests use the same
directory contract, so first-install behavior is not fixture-dependent.

### 4. Tool and Forge boundaries are explicit

Quality commands execute locked tools through `uv`; hosted CI installs only
`uv`. GitLab private assets are read through authenticated `glab api` requests
whose binary stdout is hashed directly. GitHub remains independently verified.

### 5. Runtime mutation is last and rollback-capable

Source proof and immutable release publication precede installation. The
existing 2.0.4 emergency listener is not restarted until a signed 2.0.5 payload
has been admitted. Port selection continues through configuration, CLI, and
environment mechanisms; 8792 is not copied into supervision logic.

## Rollback

If source, Forge, install, or runtime acceptance fails, keep or restore the
preceding signed payload through the transactional installer. Never repair by
changing Codex conversation state.
