# Design

Recovery owns two independently verified projections: the prior runtime frozen
in memory and the candidate already committed on disk. Canonical prose must name
both rather than overload one manifest identity.

History rewriting still signs each commit independently, but key admission is a
command-scoped capability. `run-provider-projection.sh` reuses an already loaded
exact key or creates one disposable agent, loads that provider key once through
the caller-supplied askpass bridge, executes the existing projection script, and
always terminates only the agent it created.
