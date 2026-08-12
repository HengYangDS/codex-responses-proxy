## Why

The repository quality checker applied module, function, and nesting limits only
to production Python. Large test modules and long test owners therefore passed
while the same structure was rejected in product code.

## What Changes

- Apply one structural policy to production, tests, and repository tools.
- Lower the test statement ceiling to the product ceiling.
- Split only the test modules and owners that exceed the policy, preserving
  pytest discovery and semantic ownership.

## Impact

Quality inventory, focused contract tests, and the affected test modules change.
Product runtime behavior, provider contracts, release assets, credentials, and
Codex session storage do not change.

## Out of Scope

- Coverage exclusions or threshold weakening.
- Compatibility shims, duplicate test runners, or broad ratchets.
- AIGW source changes; its equivalent Go quality atom is separate.
