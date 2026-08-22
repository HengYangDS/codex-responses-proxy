## Context

The CLI already has one dispatcher and one human renderer, but several command
owners encode absence as a generic `InstallError`. The boundary then applies a
static command-level next action, so distinct product states become the same
message even when the suggested operation is impossible.

## Goals / Non-Goals

**Goals:**

- Represent healthy absence as a successful, explicit no-op result.
- Preserve strict failure for an existing but unverifiable transaction or
  payload.
- Derive human and JSON projections from the same result dictionaries.
- Select next actions from semantic state rather than exception prose.

**Non-Goals:**

- No compatibility parser, migration path, alias, or second CLI surface.
- No automatic deletion of unknown installation content.
- No change to provider, request, credential, or native supervision protocols.

## Decisions

The lifecycle owner checks whether its exact owned carrier exists before
parsing it. Absence returns a small state result; presence continues through
the existing strict canonical parser. This avoids exception-string matching
and keeps malformed evidence fail closed.

Status remains a read-only observation. Its human renderer names absent values
as absent rather than as unknown failures and exposes the transaction state
already present in JSON. Doctor distinguishes an absent installation from a
degraded installed product and recommends installation rather than reload.
The retained runtime snapshot is trusted only when its PID is the sole owned
listener and its release, serving payload, receipt, and manifest identities
match the currently committed candidate. A live process on the configured port
is therefore not sufficient evidence of a healthy installation.

Successful command results use one `state` discriminator. Command projection
uses `state`, `kind`, and `path`; install uses `installed` or `upgraded`; reload
uses `reloaded`; recovery uses `not_required`, `closed`, `finalized`, or
`rolled_back`; uninstall uses `not_installed`, `uninstalled`, or `purged`.
Legacy boolean and `mode` projections are deleted rather than retained as
aliases.

Expected failures use one typed product-error boundary with a stable `code`, a
concise message, and exactly one executable `next` command. Diagnostic prose
belongs in the message or Human renderer, never inside the command value.

Uninstall always performs exact service, process, and command teardown first.
When no installed payload root exists, optional purge is a successful no-op.
When an unverified payload root exists without its ownership manifest, purge
continues to fail closed and preserves all bytes.

## Risks / Trade-offs

- [Automation expects `recover` to fail when idle] -> The documented result
  becomes `{"state":"not_required"}` with exit zero; invalid journals remain
  nonzero.
- [No-op uninstall could hide residue] -> It succeeds only when the payload
  root is truly absent; an existing unowned root remains an explicit error.
- [Human and JSON output drift] -> Both projections are asserted from the same
  semantic result matrix, including the native executable gate.
