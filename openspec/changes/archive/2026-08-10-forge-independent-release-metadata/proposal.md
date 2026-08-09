# Decouple release metadata verification by Forge

## Why

The GitLab `v2.0.15` pipeline failed because a repository test validated GitHub
release preparation against GitLab's checked-out tag namespace. One Forge was
therefore not operationally independent from the other.

## What Changes

- Exercise both providers from an equivalent pre-tag source checkout.
- Keep one provider-parametric metadata implementation.
- Preserve failed tags as immutable evidence; version advancement is a separate atomic Change.

## Non-goals

- No relaxation of chronology, signature, asset, or parity verification.
- No compatibility mode or provider-specific metadata implementation.
