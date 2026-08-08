# Design

The change updates existing owners rather than introducing another dependency
surface. Direct quality dependencies remain exact in `pyproject.toml`; `uv.lock`
owns their complete transitive closure. GitHub workflows keep immutable commit
pins, while adjacent comments expose the corresponding stable release for human
review. Existing contracts reject moving tags and stale artifact revisions.
