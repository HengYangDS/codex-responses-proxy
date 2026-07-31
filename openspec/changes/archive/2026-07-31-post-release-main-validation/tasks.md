## 1. Contract

- [x] 1.1 Reproduce GitLab pipeline 3959 rejecting published `v1.0.45` as a pending release.
- [x] 1.2 Add a failing contract for tag, published-main, and pending-main dispatch.

## 2. Repair

- [x] 2.1 Select ordinary provider validation when main's exact `v<VERSION>` tag exists.
- [x] 2.2 Preserve exact tag and pending-release validation paths without adding a wrapper.

## 3. Verify

- [x] 3.1 Pass focused release, presentation, provider-projection, and OpenSpec gates.
- [x] 3.2 Pass the canonical quality gate and Python 3.12/3.13/3.14 matrix above the 95% statement and branch floors.
- [x] 3.3 Pass claim integrity, evidence freshness, and diff hygiene checks.

## 4. Close out

- [x] 4.1 Hand the locally proven change to the official OpenSpec archive transition. Signed commit, exact-HEAD ETHOS proof, candidate landing, hosted Forge verification, runtime observation, repository-family record creation, and Work Lane retirement remain external closeout transitions and must be proven separately.
