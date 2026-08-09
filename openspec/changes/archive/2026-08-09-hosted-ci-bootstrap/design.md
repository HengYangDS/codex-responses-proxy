## Decision

Hosted jobs SHALL establish the locked environment before importing a
dependency-bearing repository module. Repository-only Python tools and their
tests SHALL execute through the selected interpreter's `python -m` entrypoint.

| Concern | Owner |
|---|---|
| Supported Python lines | `.python-versions` |
| Locked tool environment | `uv.lock` and the `quality` dependency group |
| Hosted projection | Forge workflow configuration |
| Regression contract | `tests/forge/test_workflow_contracts.py` |

No second matrix parser, `PYTHONPATH` injection, shell wrapper, or compatibility
package is introduced.
