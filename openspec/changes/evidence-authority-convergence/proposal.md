## Why

The repository still tracks Claim and Chronicle families after current proof
authority moved to revision-bound facts and ETHOS-selected Attestations. The
parallel taxonomy duplicates Git and OpenSpec history, creates exemptions, and
leaves stale records that look current.

## What Changes

- Remove the tracked `evidence/` root and its family policy.
- Remove Claim and Chronicle compatibility code and tests.
- Define one evidence authority chain in the canonical policy and specification.
- Retain unique historical meaning through existing OpenSpec archives,
  decisions, Changelog entries, and Git history.

## Out of Scope

- Changing runtime request or response handling.
- Implementing ETHOS Attestations inside this repository.
- Editing Codex session JSONL, SQLite, messages, or model metadata.
