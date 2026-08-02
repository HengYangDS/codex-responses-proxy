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

- [ ] 3.1 Run strict OpenSpec, release checks, quality, Python 3.12-3.14
  behavior tests, and final HEAD-bound ETHOS proof.
- [ ] 3.2 Land after the active candidate train and publish the next independent
  signed GitLab and GitHub release without reusing an existing tag.
- [ ] 3.3 Install through the released protocol-v2 transaction, switch 8792 and
  8791 only when idle, and prove listener/manifest/receipt identity.
- [ ] 3.4 Resume thread `019fc0b7-9094-7350-8772-df9a14a47a36` unchanged and
  verify multiple successful turns without `exceeded retry limit` or remote
  compaction regression.
