# Design

The job owns product-tool execution, so its environment must include both the
project and development groups from the single lock file. `uv sync --locked
--all-groups` is the existing repository-native command for that contract.

Repository quality is a package-aware tool; hosted jobs invoke it with `python -m`
so imports do not depend on script-directory semantics. Quality jobs fetch full
tag history because their canonical suite includes release chronology tests.
