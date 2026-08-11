## Why

GitHub release verification resolved the active virtual-environment interpreter
to its host Python, so the publication process lost locked dependencies.

## What Changes

- preserve the exact active interpreter path during release validation;
- cover the hosted virtual-environment boundary with a focused regression;
- forward-fix the immutable failed v2.0.24 release as v2.0.25.
