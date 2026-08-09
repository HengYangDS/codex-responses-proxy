# Make repository automation portable

## Why

Shell currently owns Forge, release, and contract behavior. That duplicates
Python owners, excludes native Windows development, and makes CI syntax part of
the product's semantic surface.

## What changes

- move Forge and release behavior into repository-native Python commands;
- move executable contracts into pytest;
- make CI invoke those owners without reimplementing them;
- delete superseded Shell files instead of retaining wrappers.

## Non-goals

- no provider, protocol, runtime, installation, or release-version change;
- no Bash and PowerShell compatibility stacks;
- no dependency on AIGW, ETHOS, Workstation, JetBrains, or Codex session data.
