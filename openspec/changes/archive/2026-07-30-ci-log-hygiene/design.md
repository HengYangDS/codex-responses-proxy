## Context

Three independent diagnostics entered successful CI logs because the jobs owned
only process exit status. The defects belonged to different semantic owners: a
production HTTP response, a deliberately disconnected loopback fixture, and a
containerized dependency installation.

## Decisions

1. Close the caught `HTTPError` where production owns it.
2. Suppress only `EPIPE`, `ECONNRESET`, and `ECONNABORTED` at the test server;
   forward every other handler exception to `socketserver`.
3. Let one runner capture and replay child output, set `PYTHONWARNINGS=error`,
   reject diagnostic banners, and compile into a temporary bytecode prefix.
4. Keep provider files as thin projections. GitLab declares pip's container
   root policy; both Forges invoke `run-python-tests.py --compile`.
5. Keep package metadata minimal. ETHOS adoption and OpenSpec live in their own
   semantic roots rather than expanding `pyproject.toml`.

## Risks / Trade-offs

- Text scanning could reject intentional warning fixtures. Such fixtures must
  capture their own output; leaked process-level diagnostics remain failures.
- Swallowing all fixture errors would hide regressions. The fixture therefore
  accepts only the three peer-disconnect errno values.
- Repository adoption adds governance files. The profile is minimal and points
  only to repository-native owners instead of duplicating commands.

## Migration Plan

1. Verify the original hosted logs and reproduce each diagnostic locally.
2. Apply owner-local fixes and regression contracts.
3. Run the full quality gate, Python 3.12/3.13/3.14 matrix, and release contracts
   with a separate forbidden-diagnostic scan.
4. Complete exact-HEAD ETHOS proof, candidate landing, accepted closeout, and
   lane retirement before dual-Forge release publication and runtime install.
