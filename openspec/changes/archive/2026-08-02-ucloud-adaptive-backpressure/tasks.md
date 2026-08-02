## 1. Contract and evidence

- [x] 1.1 Preserve the original failed-thread, provider-rate-limit, authority,
  rollback, and no-session-mutation boundaries.
- [x] 1.2 Rebase onto the signed 2.0.2 train and remove duplicate 429 work that
  is already part of the released source history.
- [x] 1.3 Scope the remaining change to monotonic cooldown deadlines.

## 2. TDD implementation

- [x] 2.1 Prove RED: a later five-second failure shortens an active 300-second
  deadline under the current implementation.
- [x] 2.2 Store the later deadline under the existing lock and prove focused
  GREEN without changing provider isolation or bounded eviction.

## 3. Source proof and lifecycle

- [x] 3.1 Run strict OpenSpec, release checks, quality, Python 3.12-3.14
  behavior tests, and final HEAD-bound ETHOS proof.
- [x] 3.2 Transfer landing and the next independent signed GitLab and GitHub
  release to the post-archive lifecycle without reusing an existing tag.
- [x] 3.3 Transfer protocol-v2 installation, idle listener switching, and
  listener/manifest/receipt identity to post-publication acceptance.
- [x] 3.4 Transfer unchanged thread
  `019fc0b7-9094-7350-8772-df9a14a47a36` continuation to post-installation
  acceptance without claiming it has already recovered.

## Post-archive lifecycle

Landing, hosted CI, signed Forge tags and Releases, asset parity, installation,
listener identity, and unchanged-thread acceptance are external transitions.
Their truth must be established from fresh ETHOS, Forge, runtime, and Codex
evidence after this completed source change is archived.
