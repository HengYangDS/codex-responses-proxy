## ADDED Requirements

### Requirement: Active provider cooldown deadlines do not move backward

For one cooldown key, a repeated or concurrent failure SHALL NOT replace a
still-active deadline with an earlier deadline. The proxy SHALL retain the later
of the current and newly computed deadlines under the existing synchronized
cache owner. It SHALL continue to purge expired entries, bound cache capacity,
and isolate unrelated provider and request-fingerprint keys.

#### Scenario: A shorter rate limit follows a longer active instruction

- **WHEN** one provider has an active 300-second cooldown and a later failure
  computes a five-second cooldown before the first deadline expires
- **THEN** the stored deadline remains the original later deadline
- **AND** upstream traffic for that provider is not reopened by the shorter
  overlapping failure.

#### Scenario: Another key receives a shorter deadline

- **WHEN** an unrelated provider or request fingerprint records a shorter
  cooldown
- **THEN** its deadline is stored independently
- **AND** the longer key is neither shortened nor copied across the boundary.
