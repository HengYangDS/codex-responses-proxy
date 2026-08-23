## Context

Cyclopts already owns conventional top-level version handling, but the current
application disables it and maintains a separate command, dispatch branch, JSON
projection, tests, and release calls for the same fact.

## Goals / Non-Goals

**Goals:**

- Use Cyclopts' native `--version` surface.
- Delete the parallel subcommand and its special dispatch/rendering paths.
- Verify the option through the installed wheel and frozen executable.

**Non-Goals:**

- Change release identity storage or version numbering.
- Add a compatibility alias for the removed command.
- Change service lifecycle or runtime state.

## Decisions

- Bind `App.version` directly to the existing `_release_version` SSOT.
- Keep `--version` human-readable and side-effect free; lifecycle JSON remains
  scoped to lifecycle commands.
- Use `--version` for installer prewarm and native release smoke so production
  and verification consume the same surface.

## Risks / Trade-offs

- Existing callers of the nonstandard `version` subcommand must switch to
  `--version`; this intentional breaking cleanup removes parallel semantics.
