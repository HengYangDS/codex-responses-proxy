# Make release identity single-sourced

## Why

The canonical release contract embeds the previous patch number. That literal
became stale as soon as the next forward release was prepared and forces an
unrelated specification edit for every patch.

## What changes

- make tracked `VERSION` the sole patch-release identity;
- state the Forge, installation, and runtime requirements against that identity;
- remove the stale `v2.0.20` literals without adding compatibility wording.

## Non-goals

- no change to SemVer, packaging, provider behavior, or publication topology;
- no rewrite of failed historical tags, runs, Releases, or logs.
