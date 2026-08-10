# Design

Commit grammar has one owner: `tools/quality/commits.py`. It selects the first
available base in semantic order:

```text
candidate/dev -> origin/dev -> origin/main -> dev -> main
```

This preserves the Work Lane boundary locally and uses only public integration
refs in Forge checkouts. If no integration ref exists, the checker validates all
available history rather than silently passing. CI workflows and branch policy
remain unchanged; no parallel configuration surface is introduced.

The published v2.0.20 identities remain immutable failed evidence. v2.0.21 is a
forward SemVer repair from one newly proven accepted source tree.
