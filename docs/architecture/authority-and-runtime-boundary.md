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
projection. `reload` first verifies the manifest, then only replaces a listener
whose command matches the installed proxy script.
