# Design

## Decision

Treat the caller-provided key path as the security authority. When its bytes
already end in a newline, pass that exact path to OpenSSH. On POSIX only, repair
the known GitLab file-variable truncation by writing one process-scoped `0600`
copy with exactly one terminal newline. Windows input that is incomplete is
passed through and rejected by OpenSSH with the existing concise diagnostic.

## Rationale

| Input | Signing path | Reason |
| --- | --- | --- |
| Complete key, any platform | Original | Preserves provider-owned permissions and ACLs. |
| Missing newline, POSIX | Ephemeral normalized copy | Repairs the observed GitLab file-variable boundary. |
| Missing newline, Windows | Original, fail closed | Avoids hand-written ACL policy and keeps secret ownership external. |

## Rejected alternatives

| Alternative | Reason |
| --- | --- |
| Rebuild Windows ACLs | Duplicates OS security policy and expands maintenance surface. |
| Always copy the key | Repeats the defect by discarding provider-owned file identity. |
| Forge-specific signing code | Creates parallel policy owners and couples the shared release contract to CI YAML. |
