# GitLab Release Dependency Forward Fix

## Why

The `v2.0.35` GitLab release pipeline completed source verification and native
asset construction, then failed before publication because its locked
environment omitted the project's runtime dependencies. The repository release
tools import Cyclopts, so a quality-only sync cannot execute them.

## What Changes

- Make the GitLab publication job install the project plus the quality group
  from the existing lock.
- Add a workflow contract that rejects another quality-only publication
  environment.
- Keep the native asset build minimal and leave product runtime behavior
  unchanged.

## Non-goals

- Changing provider routing, credentials, or the installed proxy runtime.
- Coupling GitLab publication to GitHub.
- Adding another dependency declaration or compatibility path.
