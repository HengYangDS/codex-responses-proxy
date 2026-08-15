# Design

The existing `pyproject.toml` and `uv.lock` remain the only dependency
authorities. The publication job must execute dependency-bearing repository
modules, so it synchronizes the project and the quality group through the same
locked Python identity used by the commands that follow.

The native asset build remains unchanged: its Nox release session owns the
packaging environment and already succeeds. The correction is confined to the
publisher that runs `tools/release/metadata.py` and
`tools.release.publish_gitlab`.

The regression test inspects the publication block rather than banning a token
globally. This positive contract states the required environment and keeps
unrelated minimal jobs free to use narrower dependency sets.
