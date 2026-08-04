## Context

The production history helper canonicalizes UTC to `Z`. Its independent test
oracle reconstructs the same fingerprint with `git show --format=%aI%n%cI`.
Git versions disagree only on the spelling of an exact zero offset, so raw byte
comparison creates a false failure even though both timestamps denote the same
instant.

## Goals / Non-Goals

**Goals:**

- Normalize only complete date lines ending in `+00:00` to the canonical `Z`.
- Preserve the oracle's independence from the production fingerprint function.
- Keep every tree, message, parent, non-UTC offset, and ordering byte unchanged.

**Non-Goals:**

- General date parsing or timezone conversion.
- Any production, publication, runtime, provider, or conversation mutation.

## Decisions

1. Apply one byte replacement to the Git-command oracle output before it is
   combined with the raw commit message. This exactly matches the production
   UTC spelling while retaining an external Git oracle.
2. Match only `+00:00\n`; nonzero offsets and text inside commit messages remain
   untouched.
3. Keep the fix in the existing history test rather than adding a compatibility
   helper, because the variation belongs to the external test presentation.

## Risks / Trade-offs

- A future Git version could introduce another equivalent spelling. The focused
  oracle test will expose it without changing production behavior.
- Byte replacement is intentionally narrower than a date parser, avoiding new
  normalization semantics that the product does not own.

## Rollback

Revert the single test-oracle commit. No runtime or remote state is affected.
