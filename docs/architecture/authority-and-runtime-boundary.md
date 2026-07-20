# Authority and Runtime Boundary

Status: canonical.

## Purpose

Codex DMX Proxy is a local data-plane adapter. It removes narrowly defined,
third-party-incompatible replay artifacts from outbound `/responses` requests.
It does not own conversation history, account credentials, or provider routing
policy.

## Authority model

```text
Codex Desktop       -> per-conversation model selection and transcript state
AIGW CLI            -> marked provider configuration and multi-profile projection
Codex DMX Proxy     -> loopback Responses compatibility and proxy lifecycle
Installed payload   -> generated, manifest-verified runtime projection
```

The proxy transforms a request only at the network edge. It must never repair a
conversation by mutating session JSONL, SQLite state, archives, or model
metadata. AIGW-owned marked provider blocks remain immutable to proxy route
commands.

## Runtime provenance

`install.py` copies a declared executable subset of source into `~/.codex/dmx-proxy/`,
removes only the known legacy `tests/` deployment residue, and writes
`payload-manifest.json`. The manifest contains only release identity and file
hashes for the declared executable payload: no credentials, configuration,
backups, request bodies, or logs. `control.py status --json` verifies this
projection. The portable `governance.py --json` command is a read-only view of
that same evidence. Runtime health also reports the source SHA-256 captured when
the listener loaded the proxy payload, so a new file on disk cannot be mistaken
for a reloaded process. `reload` first verifies the manifest; it then replaces
only a listener whose command matches the installed proxy script. The control
plane must close the listener's admission barrier, observe
`draining=true` and `active_responses=0` from the same verified listener, then
replace it. If that proof cannot be obtained, the listener remains serving and
the payload is not changed.

## Diagnostic boundary

The runtime status endpoint is the primary operational evidence surface. It
contains only bounded counters, classifications, and a failure timestamp. Logs
are a secondary local diagnostic surface: structured events are bounded by a
rotating retention policy and redact secret-shaped values as a defensive control.
No raw request, response, header, prompt, query value, credential, or upstream
error payload is retained. An oversized legacy segment is discarded rather than
copied into a record. Native service stdout and stderr must not form an
unbounded parallel log channel.
