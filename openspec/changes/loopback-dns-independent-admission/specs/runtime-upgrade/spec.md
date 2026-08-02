## ADDED Requirements

### Requirement: Loopback listener admission is DNS-independent

Fresh and handoff-adopted loopback listeners SHALL become serviceable without
forward, reverse, or FQDN resolution. Each listener SHALL derive its presented
host and port from the address bound by the kernel rather than from DNS.

#### Scenario: A fresh listener starts while DNS is unavailable

- **WHEN** the proxy constructs a fresh loopback listener and hostname resolution is unavailable or blocked
- **THEN** listener construction completes without consulting DNS
- **AND** the listener reports the actual bound loopback host and port
- **AND** it can proceed immediately to serve requests.

#### Scenario: A handed-off listener is adopted while DNS is unavailable

- **WHEN** an authorized runtime handoff supplies an already bound loopback socket and hostname resolution is unavailable or blocked
- **THEN** the successor adopts the socket without consulting DNS
- **AND** its reported host and port match the adopted socket's bound address.
