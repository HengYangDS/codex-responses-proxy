## 1. Closed catalog route

- [x] 1.1 Extend the provider registry with exact `models` route resolution.
- [x] 1.2 Relay the resolved catalog GET transparently without entering
  Responses-only projection, admission, retry, or recovery paths.

## 2. Contract coverage

- [x] 2.1 Add registry tests for accepted catalog routes and malformed,
  unsupported, or non-catalog targets.
- [x] 2.2 Extend the loopback fixture and route tests to assert method, upstream
  path, authentication propagation, response relay, and local rejection.
- [x] 2.3 Update operator-facing route documentation without transferring AIGW
  configuration ownership to the proxy.

## 3. Verification and repository closeout

- [x] 3.1 Run strict OpenSpec validation and focused route tests from the owned
  lane.
- [x] 3.2 Run the repository quality/proof gates required for the changed
  candidate and retain their receipts.
- [x] 3.3 Bind the source claim and transfer governed landing, publication,
  installation, and live AIGW acceptance to the post-archive lifecycle.

## Post-archive lifecycle

Landing, independent Forge publication, hosted CI, immutable signed tags and
Releases, asset identity, transactional installation, live `aigw check`, live
`aigw catalog`, a DMXAPI Responses request, and original-task continuation are
separate external transitions. None is complete without fresh external evidence.
