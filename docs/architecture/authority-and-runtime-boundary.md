# Authority and Runtime Boundary

Status: canonical.

## Purpose

Codex DMX Proxy is a local data-plane adapter. It removes narrowly defined,
third-party-incompatible replay artifacts from outbound `/responses` requests.
It does not own conversation history, account credentials, provider routing
policy, or publication truth.

## Authority model

```text
Codex Desktop        -> per-conversation model selection and transcript state
AIGW CLI             -> marked provider configuration and multi-profile projection
GitLab + GitHub      -> independent signed tags, CI, and Release records
Released checkout    -> source admission and payload lifecycle composition
Installed control    -> read-only evidence, route control, same-payload reload
Listener             -> loopback Responses compatibility and handoff state
```

The proxy transforms requests only at the network edge. It must never repair a
conversation by mutating session JSONL, SQLite state, archives, or model
metadata. AIGW-owned marked provider blocks remain immutable to proxy route
commands.

The pure policy in `proxy/input_compatibility.py` owns the exact observed
Responses input-union failure. Transport orchestration may invoke that policy
once to construct a strictly smaller network request from the latest system,
developer, and user messages plus top-level instructions. No stored transcript
is rewritten, and the resulting attempt cannot cross into another retry or
reconnect policy.

## Released-source admission

Installation is permitted only after the source-side installer itself verifies
the provider-native signed GitLab and GitHub tags, required hosted CI jobs,
formal Release records, and common source tree. The evidence-only
`scripts/verify-publication-proof.py` exposes the same observation without
minting reusable authority. The installer then verifies that checkout `HEAD` is the exact signed
annotated `v<VERSION>` tag under an external allowed-signers anchor.

`platform_adapters.release_source` reads immutable Git objects rather than
working-tree payload bytes and returns an opaque, immutable, one-use release
capability. That capability binds the tag object, commit, tree, dual-Forge
publication evidence, payload blobs and modes, aggregate serving-payload digest,
and canonical receipt. A release archive, arbitrary directory, working-tree
stage, or installed controller cannot create that capability.

## Payload transaction and provenance

`platform_adapters.payload` consumes the capability once. It owns the private
sibling transaction, exact rollback snapshot, canonical release receipt,
manifest, installed-release state, and recovery-required journal. The manifest
covers only declared executable files and records release identity, per-file
digests, the canonical aggregate serving-payload digest, and the release-receipt
digest. Configuration, backups, logs, request data, credentials, and route state
are outside the payload transaction.

A fresh installation or replacement finalizes only after one accepting listener
proves the expected release, aggregate serving-payload digest, receipt digest,
and manifest digest. A pre-finalize failure restores the exact prior owned
projection. If a committed handoff outcome cannot be proved, the transaction is
preserved as recovery-required rather than guessed successful or rolled back
blindly.

`control.py status --json` and portable `governance.py --json` are read-only
views of installed integrity, route authority, listener identity, transaction
state, and startup-frozen runtime identity. The `proxy/` directory remains an
installed script-directory module set, not a Python package or compatibility
facade.

## Lifecycle ownership

Installed `control.py reload` is same-payload only. It verifies the installed
manifest and receipt, prepares a non-accepting protocol-v2 child, stops the old
accept loop before `COMMIT`, and proves PID, transaction, release, aggregate
payload, receipt, manifest, and accepting state before `FINALIZE`. The listening
socket remains open. Accepted handlers drain to zero or the bounded lease; a
pre-finalize failure resumes old admission only after child exit is confirmed.
An unconfirmed abort fails closed.

A different release is installed only by source-side `install.py`. After release
admission and transaction commit, `platform_adapters.deployment` uses the same
protocol-v2 handoff owner and runtime identity proof. Installed control exposes
no arbitrary stage-path upgrade or controller-only partial apply.

The sole compatibility exception is source-side replacement of a verified
listener that predates protocol-v2 handoff. It requires explicit
`--allow-legacy-bootstrap` authorization and a bounded zero-active quiet window
on the same PID before payload mutation. `--force-legacy-bootstrap` is a separate
interruption authorization; it still requires manifest integrity and exactly
one verified legacy listener. Neither flag applies to same-payload reload or a
current protocol-v2 listener.

## Diagnostic boundary

Runtime status contains only bounded counters, classifications, provenance
digests, and timestamps. Logs are a secondary local diagnostic surface:
structured events are bounded by rotating retention and redact secret-shaped
values. No raw request, response, header, prompt, query value, credential, or
upstream error payload is retained. Retired raw-capture filenames are removed
without reading their contents; oversized legacy log segments are discarded
rather than copied into evidence. Native service stdout and stderr must not form
an unbounded parallel log channel.

Input-union diagnostics contain closed-enum type counts, call/output pairing
state, the first detected incompatibility category, and a hash of a capped
categorical shape. Unknown names, values, and exact collection cardinalities
are erased before hashing or diagnostic logging. Recovery events may retain
exact byte lengths and retained or dropped item counts, but never the
corresponding message values or unknown names.
