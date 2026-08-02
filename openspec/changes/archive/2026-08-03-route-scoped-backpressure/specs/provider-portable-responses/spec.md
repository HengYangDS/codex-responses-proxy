## ADDED Requirements

### Requirement: Provider route admission closes concurrent rate-limit bursts

The proxy SHALL admit at most one active Responses exchange per provider route
while allowing different provider routes to proceed concurrently within the
configured global limit. After a queued request acquires its provider route, it
SHALL recheck that provider's cooldown before remote I/O. HTTP 429 SHALL remain
terminal for the current request and SHALL NOT introduce an upstream retry.

#### Scenario: Concurrent requests target one provider route

- **WHEN** two Responses requests overlap on the same configured provider route
- **THEN** only one request performs provider I/O at a time
- **AND** the second request remains locally queued until the first releases the
  route or its bounded queue wait expires.

#### Scenario: Different provider routes overlap

- **WHEN** Responses requests overlap on two different configured provider
  routes and global capacity remains
- **THEN** both routes can perform provider I/O concurrently
- **AND** neither route's admission slot blocks the other route.

#### Scenario: Leading request establishes cooldown

- **WHEN** a queued request acquires its route after the preceding request has
  recorded a provider rate-limit cooldown
- **THEN** the queued request receives the existing local HTTP 429 response
- **AND** the proxy makes no upstream call for that queued request.
