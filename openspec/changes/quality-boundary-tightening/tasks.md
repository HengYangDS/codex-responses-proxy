## 1. Positive quality boundary

- [x] 1.1 Apply structural limits to tests and reduce the test statement ceiling.
- [x] 1.2 Add regression coverage proving tests cannot bypass module, function,
  or nesting limits.

## 2. Semantic debt removal

- [x] 2.1 Split `tests/quality/test_contract.py` by quality concern.
- [x] 2.2 Split `tests/relay/test_exchange.py` by transport/recovery concern.
- [x] 2.3 Split other over-limit test owners without changing discovery or
  behavior.
- [x] 2.4 Keep all moved tests within the declared semantic package owner.

## 3. Acceptance

- [x] 3.1 Pass the focused quality-contract suite.
- [ ] 3.2 Pass quick, quality, Python 3.12/3.13/3.14, and release sessions.
- [ ] 3.3 Produce exact-HEAD proof, archive, and candidate/accepted land.

## Requirement To Task To Proof

| Requirement | Task | Proof |
| --- | --- | --- |
| `quality-boundaries:One structural quality boundary` | `1.1` | `repository-quality` |
