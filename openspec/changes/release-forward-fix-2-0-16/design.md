# Design

The failed tag is immutable. The next patch changes only release identity and
its user-facing asset example; it consumes the already proven source fix.

| Input | Terminal state |
| --- | --- |
| Failed `v2.0.15` | Preserved evidence |
| Provider-isolation fix | Accepted source |
| `VERSION`, Changelog, README | Consistent `2.0.16` release train |

No runtime code, provider adapter, signing path, or compatibility surface is
introduced.
