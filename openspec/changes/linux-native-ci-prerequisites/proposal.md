## Why

GitLab pipeline `4489` proved that the repository's native executable tests
were not reproducible on the declared minimal Linux image: PyInstaller requires
Linux `objdump`, but the projection relied on an undeclared runner image layer.

## What Changes

- Install the Linux native-object inspection tool in every GitLab job that
  invokes the repository-owned native executable gate.
- Add a contract test that prevents the dependency from disappearing from
  either the Python matrix or quality projection.
- Preserve Nox as the only verification composition owner; this change adds no
  product dependency or runner-specific selector.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-diagnostics`: subject=minimal hosted Linux native-build prerequisites;
  reuse=extend; change=modify; facet:lifecycle=validation,release;
  facet:surface=ci,test; facet:authority=source,test,openspec,claim,evidence.

## Impact

Only `.gitlab-ci.yml`, its release-metadata contract test, and the active
terminal closeout evidence are affected. GitHub, product runtime, provider
protocols, Codex history, and release identity are unchanged.

## Out of Scope

- Replacing the repository-owned Nox/PyInstaller build.
- Encoding a private runner image, label, path, or workstation policy in the
  repository.
- Treating the repair as proof of hosted success before a new exact-head
  pipeline completes.
