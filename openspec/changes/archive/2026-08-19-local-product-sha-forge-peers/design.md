## Authority model

```text
local signed Git objects
        ├── exact-CAS → GitLab
        └── exact-CAS → GitHub
```

Local Git is the only product source. A Forge supplies transport, CI, Release,
and account verification; it never supplies a source commit or alternate history.

## Projection

The projector reads one local source ref and the selected remote's current branch
coordinates. It verifies the local commit's author/committer email and SSH
signature against the selected Forge context, then atomically pushes the same
commit object to the allowed remote refs using per-ref `--force-with-lease` for the
one-time destructive cutover. Subsequent calls remain exact and idempotent.

`main` publishes `main` and `dev`; `proposal/*` publishes only that proposal ref.
`candidate/dev` and `work/*` are rejected. A missing remote branch uses the zero
OID lease. A changed remote tip causes the push to fail and requires re-observation.

## Tags

The local tag is the sole tag object. Tag publication verifies its annotation,
peeled commit, and signature against the selected Forge trust anchor, then pushes
that exact tag without force. An existing different tag object fails closed.

## Audit

The parity audit compares exact `main`/`dev` commit OIDs, trees, tag OIDs, asset
hashes, and provider-native CI/Release facts. Historical provider prefixes are
not a current authority and are not mapped or repaired.

## Non-goals

- no Forge-to-Forge reads or publication;
- no provider-specific commit recreation;
- no compatibility aliases for removed replay and continuity flags;
- no changes to client configuration, Codex state, or runtime payloads.
