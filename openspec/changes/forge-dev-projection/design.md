# Design

The projector already constructs and verifies one provider-native commit in an
isolated clone. Reuse that commit as the sole source for an atomic two-ref push:

```text
accepted source -> provider-native signed commit -> {main, dev}
```

This keeps one semantic owner. A second script, post-projection raw push, or
Forge-to-Forge synchronization would create a parallel publication path and is
therefore rejected.

Atomic push ensures neither protected branch advances alone. Existing remote
history admission remains unchanged: every new provider commit is append-only,
signed by the selected external identity, and tree-equivalent to accepted
source.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `product-interface:Local product closure is Forge-free` | `1.1` | `python-quality` |
