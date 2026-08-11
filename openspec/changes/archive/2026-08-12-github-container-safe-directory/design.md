# Design

`git -c safe.directory="$GITHUB_WORKSPACE" archive ...` binds trust to one
process and one exact checkout path. It does not mutate repository, user, or
system Git configuration and cannot authorize another directory.

The existing canonical `/workspace` materialization and immutable Linux runtime
remain unchanged. v2.0.26 stays as failed release evidence; v2.0.27 is a
forward-only SemVer patch.
