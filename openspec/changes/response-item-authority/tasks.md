## 1. Contract

- [x] 1.1 Add failing contract tests proving recognized item kinds cannot be diagnosed as known and projected as unknown, while genuinely unknown kinds still fail closed.

## 2. Authority

- [x] 2.1 Introduce one immutable typed item policy that owns classification, projection strategy, and call/output relationships; keep shape validation in the request projector and verify both boundaries in focused tests.
- [x] 2.2 Migrate diagnostics and request projection to consume the policy, delete their parallel item-kind registries, and pass focused protocol and relay tests.

## 3. Verification

- [x] 3.1 Run formatting, lint, type, and affected test gates with no warning or failure.
- [x] 3.2 Validate the OpenSpec Change and produce exact-HEAD ETHOS proof without modifying the installed 3.1.11 service.
