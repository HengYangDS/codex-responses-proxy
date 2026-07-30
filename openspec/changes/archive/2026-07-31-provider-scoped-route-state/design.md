## Context

The provider-portable data plane has three canonical AIGW bases:

```text
http://127.0.0.1:<port>/dmxapi/v1
http://127.0.0.1:<port>/ucloud/v1
http://127.0.0.1:<port>/aihubmix/v1
```

The route-state control plane predates those namespaces. Its single
`proxy_base_url()` helper returns `http://127.0.0.1:<port>/v1`; schema-v2 AIGW
state stores that value, `adopt-aigw` accepts only that value or the direct URL,
and enable reuses the stored value. A canonical scoped AIGW endpoint consequently
appears drifted even though listener routing and AIGW projection are correct.
The controller also extracts the port by removing a terminal `/v1` from the
whole authority-and-path suffix, which cannot parse a scoped non-default port.

The unscoped route still has one bounded purpose: direct Codex compatibility and
the migration ordering that keeps an older live client connected while the
released listener and AIGW projection are changed. It is not a canonical AIGW
route and must not remain an AIGW route-state dependency.

## Goals / Non-Goals

**Goals:**

- Make every newly written AIGW state identify exactly one canonical provider
  route and scoped loopback base.
- Migrate valid schema-v2 AIGW state through one explicit, owner-correct command
  without editing AIGW configuration directly.
- Keep exact drift detection, direct restoration, and uninstall reversibility.
- Preserve legacy direct-Codex `/v1` behavior without allowing it to leak back
  into canonical AIGW state.
- Parse both scoped and legacy loopback state safely at any valid listener port.

**Non-Goals:**

- Removing the unscoped listener route in the same release.
- Managing all AIGW accounts in one proxy state record or using route control to
  switch the active provider.
- Inferring a provider route from a mutable AIGW account name.
- Rewriting conversation storage, model metadata, credentials, or AIGW-managed
  consumer projections.

## Decisions

### 1. Schema v3 separates AIGW account identity from provider route identity

An AIGW schema-v3 state retains `aigw_config_path`, `aigw_account`,
`direct_url`, and `proxy_url`, and adds `provider_route`. `provider_route` is a
closed enum containing `dmxapi`, `ucloud`, and `aihubmix`. The AIGW account is an
external control-plane identifier and may be renamed; it is therefore never
used to infer the data-plane namespace.

For `route_mode = "aigw_endpoint"`, validation requires:

```text
proxy_url == http://127.0.0.1:<context-port>/<provider_route>/v1
```

Unknown routes, a mismatched URL, a non-loopback host, or a different port fail
closed. The complete URL remains recorded so status and transitions can compare
an exact authorized value; `provider_route` makes its semantics independently
checkable rather than relying on string shape alone.

The existing `codex_config` direct mode remains the bounded legacy mode. Its
unscoped `/v1` URL and exact file-hash restoration contract do not become an
AIGW schema-v3 route and are not generalized to the other providers.

### 2. Canonical and legacy URL constructors remain distinct

Production code gains a provider-scoped constructor whose only accepted route
names are the three release-owned providers. The existing unscoped constructor
is retained only for direct-Codex compatibility and schema-v1/v2 migration.
New AIGW state construction, adoption, status, enable, and uninstall restoration
must use the scoped constructor. No AIGW path may silently fall back to `/v1`.

Schema-v1 direct state and schema-v2 direct or AIGW state remain readable so an
upgrade does not destroy recorded rollback authority. Legacy AIGW state is not
silently rewritten while loading: a read-only status must not become a hidden
mutation, and a stale `/v1` record is not sufficient authority to manufacture a
provider route.

### 3. Existing `adopt-aigw` is the sole schema-v2 to schema-v3 migration entry

`adopt-aigw` receives an explicit AIGW account, direct URL, and provider route.
It resolves and reads the canonical AIGW configuration, then accepts migration
only when the selected account endpoint equals either:

1. the normalized exact direct URL, representing a disabled route; or
2. the exact scoped loopback URL derived from the selected provider route and
   installed listener port, representing an enabled route.

It then atomically replaces the proxy-owned record with validated schema-v3
state and reclassifies the canonical endpoint against that state. It never
writes AIGW configuration. If the canonical endpoint is still the unscoped
`/v1` migration route, the operator must first use AIGW's public CLI and sync
lifecycle to project the scoped endpoint, then rerun `adopt-aigw`. An unrelated
endpoint remains drift and is never adopted by guessing.

The command keeps `dmxapi` as the ergonomic default provider route and aligns
its default account with the governed `dmxapi` account. Explicit UCloud or
AIHubMix adoption requires the matching provider route and exact direct URL.

### 4. Legacy state cannot reintroduce an unscoped AIGW route

A valid schema-v2 AIGW record remains available for diagnosis and exact removal,
but it cannot authorize an enable transition that writes `/v1`. If its route is
disabled or the canonical endpoint has already moved to a scoped namespace, the
operator uses `adopt-aigw` to mint schema-v3 state before enabling or otherwise
controlling the AIGW route.

An exact disable or uninstall restoration from a still-enabled legacy state may
delegate restoration to the recorded direct URL because that transition removes
the migration route rather than recreating it. Drift, missing state, a changed
direct URL, or an unverified AIGW result continues to preserve state and fail
closed.

### 5. Port discovery parses the loopback URL structurally

Installed control parses `proxy_url` with a URL parser and accepts only HTTP,
host `127.0.0.1`, a valid explicit port, and either the bounded legacy path or
one canonical provider path. It does not derive the port with suffix slicing and
does not accept credentials, query, fragment, another host, or an unknown route.
Invalid state leaves the controller on its validated default without granting
route authority.

### 6. TDD proves the source gap before implementation

Focused tests first require scoped AIGW construction and adoption, schema-v2 to
schema-v3 migration, scoped enable, exact direct disable, provider allowlisting,
and custom-port discovery. The unchanged production code must fail those tests
for the expected unscoped-route reasons before implementation begins. Existing
legacy direct-route and drift-refusal tests remain green throughout.

OpenSpec remains the only persistent plan and specification authority. TDD,
systematic debugging, and verification methods guide execution but create no
parallel repository plan.

## Risks / Trade-offs

- **Schema v3 is unreadable to older control code** -> migrate state only after
  the v1.0.44 successor runtime is fully proved; protocol-v2 rollback therefore
  completes before route-state migration begins.
- **Account names and provider routes can diverge** -> store and validate them as
  separate fields and require an explicit provider route during adoption.
- **A legacy enable could recreate `/v1`** -> prohibit AIGW enable from schema-v2
  state and require `adopt-aigw` first.
- **Automatic loading could hide an external change** -> keep loading read-only
  and make schema migration an explicit atomic command.
- **Direct legacy mode remains a control-plane exception** -> bound it to the
  existing Codex-config compatibility path and prohibit its constructor from all
  AIGW schema-v3 paths.
- **A route-state migration could be mistaken for provider switching** -> retain
  AIGW as the provider/account selector and document adoption as reversible
  state registration only.

## Migration Plan

1. Add the focused RED expectations while production still records unscoped
   AIGW state, and retain the failure evidence.
2. Implement schema-v3 validation, scoped AIGW URL construction, explicit
   adoption, legacy transition guards, and structural port parsing; pass focused
   and full supported-Python gates.
3. Land the source-only change into the untagged v1.0.44 train and refresh the
   active runtime-acceptance carrier onto the new proved source identity.
4. Publish and install v1.0.44 through the existing dual-Forge and protocol-v2
   gates. Do not migrate route state before successor proof finalizes.
5. Use AIGW's public CLI and sync lifecycle to ensure each account has its exact
   scoped endpoint. Run installed `adopt-aigw` for the selected managed route,
   then verify schema v3, scoped URL, route status, and unchanged direct rollback
   target.
6. Resume the unchanged-original-conversation provider sequence only after
   runtime, AIGW, and route-state evidence agree.

If source installation fails, the existing payload transaction restores the
v1.0.43 projection before any schema-v3 migration is attempted. If adoption
fails, the canonical AIGW configuration remains untouched and the prior
proxy-owned state is retained or the atomic state replacement fails as a unit.
After schema-v3 adoption, any deliberate payload downgrade must first restore or
otherwise retire that state through the fixed controller; v1.0.43 control is not
treated as schema-v3 rollback authority.
