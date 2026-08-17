# Design

## Small Documentation Kernel

Proxy retains five information domains:

| Domain | Owns |
| --- | --- |
| `architecture/` | Product boundary, provider admission, and runtime projection |
| `decisions/` | Durable decisions and their semantic register |
| `evidence/` | Proof policy and bounded validation records |
| `governance/` | Change and release policy |
| `operations/` | Independent Forge operation |

`docs/README.md` is the sole directory index. The Decision Record register and
evidence policy are content documents, so their filenames state their subjects.
Single-document domains remain direct links rather than gaining redundant
local indexes.

## Executable Alignment

The Decision Record checker names `decision-register.md` explicitly. Release
metadata lists the two semantic paths. Tests use the same names. This keeps one
physical and logical structure instead of preserving `README.md` as a hidden
parallel convention.

## Migration

Files move without compatibility copies. All current tracked links and path
consumers change atomically; repository link, quality, and release checks prove
closure.
