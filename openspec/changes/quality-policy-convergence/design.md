# Design

## Risk Boundary

Aggregate coverage detects broad blind spots. Semantic-package coverage keeps
one well-tested domain from hiding another domain's untested behavior. Individual
file ratios are unstable under cohesive refactoring and do not represent an
independent product boundary.

## Single Authority

| Surface | Responsibility |
| --- | --- |
| `.config/checks/coverage/policy.toml` | Floor, comparison, scopes, metrics, risk, cost, remediation, review |
| `.config/checks/coverage/coverage.ini` | coverage.py collection and report formatting |
| `tools/quality/branch_coverage.py` | Exact aggregate and semantic-package evaluation |
| `ci-diagnostics` | Composition and host-independent execution |
| `quality-boundaries` | General rule-admission and ownership contract |

The retired module evaluator is deleted rather than retained behind an alias or
compatibility flag.

## Review Trigger

The floor is reviewed when repeated legitimate changes are blocked solely by
semantic-package denominator granularity, or when the protocol/lifecycle risk
boundary changes. Review updates the one policy; it never creates exclusions.
