## Context

The v2.0.30 GitHub and GitLab Linux archives differed although their source
trees, pinned container image, Python runtime, and ordinary bundle members
matched. The product distribution's `RECORD` retained the digest of
installer-local `uv_cache.json`; the frozen executable also differed. Removing
those files only while assembling the outer archive is therefore too late.

## Goals / Non-Goals

**Goals:**

- Give the release session one deterministic installed-distribution input.
- Prove the normalization rejects unknown or malformed product metadata.
- Preserve independent Forge construction and publication.

**Non-Goals:**

- Sharing build artifacts between Forge planes.
- Making arbitrary native toolchains reproducible.
- Rewriting the immutable v2.0.30 publication.

## Decisions

### Normalize the installed product before freezing

The release session removes the two known installer-provenance files from the
installed product distribution and rewrites `RECORD` from the remaining exact
files before invoking PyInstaller. This repairs the semantic owner rather than
post-processing an already contaminated executable.

Alternatives rejected:

- Binary patching is format-specific and cannot prove semantic completeness.
- Ignoring executable digest differences would preserve a false release claim.
- Sharing one Forge's Linux artifact would couple otherwise independent planes.

### Test the freeze input, then audit published bytes

A focused test creates equivalent installed distributions with different
provenance and requires normalization to yield identical metadata. Hosted
publication remains responsible for native construction; the closeout audit
compares the independently published bytes.

## Risks / Trade-offs

- **Installer metadata evolves** -> fail closed when the product distribution
  or its inventory is absent or malformed, and keep the accepted provenance
  names explicit in the release owner.
- **Native compiler nondeterminism remains** -> published byte comparison is
  the terminal check; any residual difference blocks installation and triggers
  another bounded diagnosis.

## Migration Plan

Publish one SemVer patch without changing v2.0.30. Verify both independent
Forge releases and common-platform digest parity before upgrading the installed
runtime. Rollback remains the existing signed-asset transaction.
