## Context

The repository publishes one native executable, but its Python support contract
belongs to the wheel source and installed console entrypoint. PyInstaller
onefile extraction is a native distribution concern, not a Python-version
compatibility invariant.

## Decisions

1. Every Python session builds and installs the wheel, then uses that
   environment's `codex-responses-proxy` console executable for subprocess
   behavior tests.
2. `CODEX_RESPONSES_PROXY_EXECUTABLE` denotes the executable used by behavior
   fixtures; it does not claim native or no-Python semantics.
3. `CODEX_RESPONSES_PROXY_NATIVE_EXECUTABLE` denotes only the PyInstaller binary
   used by native black-box assertions.
4. The release session is the sole `_build_executable` caller and runs both the
   CLI interface tests and real handoff integration tests before packaging.
5. OpenSpec carriers contain only work completed before archive. Candidate
   landing and later transitions remain active-claim obligations; they are not
   unchecked archive tasks and are never marked complete before execution.

## Risks / Trade-offs

- The wheel console executable requires its session Python by design; native
  independence remains separately and explicitly proved by the release session.
- Release verification becomes the only native handoff owner, so its focused
  test list must remain protected by structural contracts.

## Migration Plan

Add structural RED contracts, separate the two executable identities, repair
the malformed pre-archive task boundary, run focused behavior tests, then run
quick, quality, Python matrix, release, strict OpenSpec, and exact-head ETHOS
proof. Archive the completed carrier before candidate landing; keep landing and
later transitions explicitly unproved in the active claim until executed.
