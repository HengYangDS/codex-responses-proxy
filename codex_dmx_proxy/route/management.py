"""Reversible Codex and AIGW route state.

This module owns route validation, recorded state, canonical AIGW observation,
and exact reversible transitions.  It does not own runtime payload deployment.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import urllib.parse
from collections.abc import Mapping
from typing import cast

from codex_dmx_proxy import installation
from codex_dmx_proxy import errors


STATE_FILENAME = "install-state.json"
STATE_SCHEMA_VERSION = 3
AUXILIARY_STATE_FILES = (STATE_FILENAME,)
AIGW_PROVIDER_BEGIN = "# >>> AIGW managed provider >>>"
AIGW_PROVIDER_END = "# <<< AIGW managed provider <<<"
PROVIDER_ROUTES = frozenset(("dmxapi", "ucloud", "aihubmix"))
_BASEURL_RE = re.compile(
    r'^(?P<indent>\s*)base_url\s*=\s*(?P<q>["\'])(?P<url>.*?)(?P=q)\s*(?P<comment>#.*)?$'
)


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def read_base_urls(config_text: str) -> list[str]:
    """Return every base_url value found (order preserved)."""
    out = []
    for line in config_text.splitlines():
        m = _BASEURL_RE.match(line)
        if m:
            out.append(m.group("url"))
    return out


def rewrite_base_url(config_text: str, old_host_substr: str, new_base_url: str) -> tuple[str, int]:
    """Rewrite base_url lines whose value contains ``old_host_substr`` to
    ``new_base_url`` (preserving indentation and quote style). Returns
    (new_text, num_changed). Lines already set to new_base_url are left as-is.

    This is quote/whitespace tolerant (a proper line-structured rewrite), unlike a
    fixed-string sed which breaks if the user's quoting differs.
    """
    changed = 0
    out_lines = []
    for line in config_text.splitlines(keepends=True):
        ending = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
        body = line[: -len(ending)] if ending else line
        m = _BASEURL_RE.match(body)
        if m and old_host_substr in m.group("url") and m.group("url") != new_base_url:
            q = m.group("q")
            comment = m.group("comment") or ""
            out_lines.append(
                f"{m.group('indent')}base_url = {q}{new_base_url}{q}"
                + (f" {comment}" if comment else "")
                + ending
            )
            changed += 1
        else:
            out_lines.append(line)
    return "".join(out_lines), changed


def legacy_dmx_proxy_base_url(port: int) -> str:
    """Return the bounded unscoped DMX migration URL used by direct Codex mode."""
    return f"http://127.0.0.1:{port}/v1"


def provider_proxy_base_url(port: int, provider_route: str) -> str:
    """Return one canonical provider-scoped loopback Responses base URL."""
    if provider_route not in PROVIDER_ROUTES:
        raise errors.InstallError("provider route must be dmxapi, ucloud, or aihubmix")
    return f"http://127.0.0.1:{port}/{provider_route}/v1"


def normalize_upstream_url(value: str) -> str:
    """Validate a service-safe remote HTTP(S) upstream URL.

    The value is propagated into shell-adjacent Windows and service definitions;
    reject whitespace, control characters and quote-like metacharacters rather
    than relying on each platform renderer to repair unsafe input.
    """
    if not isinstance(value, str) or not value:
        raise errors.InstallError("upstream must be a non-empty HTTP(S) URL")
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise errors.InstallError("upstream URL cannot contain whitespace or control characters")
    if any(
        character in value
        for character in (
            '"',
            "'",
            "%",
            "!",
            "^",
            "&",
            "|",
            "<",
            ">",
            "`",
            "$",
            "\\",
            "(",
            ")",
            ";",
        )
    ):
        raise errors.InstallError("upstream URL contains unsafe characters")
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise errors.InstallError("upstream must be an absolute HTTP(S) URL with a hostname")
        if parsed.username is not None or parsed.password is not None:
            raise errors.InstallError("upstream URL cannot include user credentials")
        if parsed.query or parsed.fragment:
            raise errors.InstallError("upstream URL cannot include a query or fragment")
        if parsed.path and not parsed.path.startswith("/"):
            raise errors.InstallError("upstream URL path must be absolute")
        port = parsed.port  # validates an explicit numeric port in range
        if port == 0:
            raise errors.InstallError("upstream URL port must be in 1..65535")
    except ValueError as exc:
        raise errors.InstallError("upstream URL has an invalid port") from exc
    return value.rstrip("/")


def install_state_path(ctx: installation.InstallContext) -> str:
    """Return the reversible route-state record path for this installation."""
    return os.path.join(ctx.install_dir, STATE_FILENAME)


def _atomic_write_text(path: str, content: str) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    temporary = f"{path}.tmp-{os.getpid()}"
    try:
        with open(temporary, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.remove(temporary)
        except FileNotFoundError:
            pass


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_install_state(
    ctx: installation.InstallContext,
    *,
    backup_path: str,
    direct_text: str,
    enabled_text: str,
    source_host_substr: str = "dmxapi",
) -> dict:
    """Construct the non-secret record authorizing reversible route changes."""
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "route_mode": "codex_config",
        "config_path": os.path.abspath(ctx.codex_config),
        "backup_path": os.path.abspath(backup_path),
        "proxy_url": legacy_dmx_proxy_base_url(ctx.port),
        "source_host_substr": source_host_substr,
        "direct_sha256": _sha256_text(direct_text),
        "enabled_sha256": _sha256_text(enabled_text),
    }


def make_aigw_install_state(
    ctx: installation.InstallContext,
    *,
    aigw_config_path: str,
    account: str,
    direct_url: str,
    provider_route: str = "dmxapi",
) -> dict:
    """Construct an AIGW-owned endpoint route record without retaining secrets."""
    if not isinstance(account, str) or not account:
        raise errors.InstallError("AIGW account must be non-empty")
    proxy_url = provider_proxy_base_url(ctx.port, provider_route)
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "route_mode": "aigw_endpoint",
        "aigw_config_path": os.path.abspath(aigw_config_path),
        "aigw_account": account,
        "provider_route": provider_route,
        "proxy_url": proxy_url,
        "direct_url": normalize_upstream_url(direct_url),
    }


def _valid_install_state(ctx: installation.InstallContext, state: object) -> bool:
    if not isinstance(state, Mapping):
        return False
    state = cast(Mapping[str, object], state)
    schema_version = state.get("schema_version")
    route_mode = state.get("route_mode")
    # v1 contained only direct Codex-config state. v2 added AIGW state but could
    # represent only the unscoped DMX migration URL. Both remain read-only
    # migration shapes; every newly written state uses schema v3.
    if schema_version == 1 and route_mode is None:
        route_mode = "codex_config"
    elif schema_version not in (2, STATE_SCHEMA_VERSION):
        return False
    if route_mode == "codex_config":
        if state.get("config_path") != os.path.abspath(ctx.codex_config):
            return False
        if state.get("proxy_url") != legacy_dmx_proxy_base_url(ctx.port):
            return False
        backup = state.get("backup_path")
        if not isinstance(backup, str) or not backup.startswith(
            os.path.abspath(ctx.codex_config) + ".bak-"
        ):
            return False
        source_host_substr = state.get("source_host_substr")
        if not isinstance(source_host_substr, str) or not source_host_substr:
            return False
        direct_sha256 = state.get("direct_sha256")
        enabled_sha256 = state.get("enabled_sha256")
        return (
            isinstance(direct_sha256, str)
            and len(direct_sha256) == 64
            and isinstance(enabled_sha256, str)
            and len(enabled_sha256) == 64
        )
    if route_mode == "aigw_endpoint":
        if schema_version == 1:
            return False
        aigw_config_path = state.get("aigw_config_path")
        aigw_account = state.get("aigw_account")
        direct_url = state.get("direct_url")
        if schema_version == 2:
            proxy_url_is_valid = state.get("proxy_url") == legacy_dmx_proxy_base_url(ctx.port)
        else:
            provider_route = state.get("provider_route")
            proxy_url_is_valid = (
                isinstance(provider_route, str)
                and provider_route in PROVIDER_ROUTES
                and state.get("proxy_url") == provider_proxy_base_url(ctx.port, provider_route)
            )
        return (
            isinstance(aigw_config_path, str)
            and os.path.isabs(aigw_config_path)
            and isinstance(aigw_account, str)
            and bool(aigw_account)
            and proxy_url_is_valid
            and isinstance(direct_url, str)
            and _is_valid_upstream_url(direct_url)
        )
    return False


def write_install_state(ctx: installation.InstallContext, state: dict) -> None:
    """Atomically persist one validated, non-secret route-state record."""
    if not _valid_install_state(ctx, state):
        raise errors.InstallError("refusing to write invalid proxy install state")
    _atomic_write_text(install_state_path(ctx), json.dumps(state, sort_keys=True) + "\n")


def load_install_state(ctx: installation.InstallContext) -> dict | None:
    """Load a valid route-state record, or return no managed state."""
    try:
        with open(install_state_path(ctx), "r", encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    return state if _valid_install_state(ctx, state) else None


def remove_install_state(ctx: installation.InstallContext) -> None:
    """Remove only this installation's reversible route-state record."""
    try:
        os.remove(install_state_path(ctx))
    except FileNotFoundError:
        pass


def route_status(ctx: installation.InstallContext, state: dict | None) -> str:
    """Classify the configured route as enabled, disabled, drifted, or unmanaged."""
    if state is None:
        return "unmanaged"
    if state.get("route_mode") == "aigw_endpoint":
        return aigw_route_status(ctx, state, state["aigw_config_path"])
    try:
        with open(ctx.codex_config, "r", encoding="utf-8") as fh:
            current = fh.read()
    except OSError:
        return "drifted"
    current_sha256 = _sha256_text(current)
    if current_sha256 == state["enabled_sha256"]:
        return "enabled"
    if current_sha256 == state["direct_sha256"]:
        return "disabled"
    return "drifted"


def _is_valid_upstream_url(value: str) -> bool:
    try:
        normalize_upstream_url(value)
    except errors.InstallError:
        return False
    return True


def aigw_endpoint(config_text: str, account: str) -> str | None:
    """Read the account's responses endpoint from canonical AIGW TOML text."""
    section = f"[accounts.{account}.endpoints]"
    in_section = False
    for line in config_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == section
            continue
        if not in_section:
            continue
        match = re.match(r'^\s*openai_responses\s*=\s*(["\'])(.*?)\1\s*(?:#.*)?$', line)
        if match:
            return match.group(2)
    return None


def aigw_route_status(ctx: installation.InstallContext, state: dict, config_path: str) -> str:
    """Classify the canonical AIGW endpoint against recorded route state."""
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            endpoint = aigw_endpoint(fh.read(), state["aigw_account"])
    except OSError:
        return "drifted"
    if state.get("schema_version") == 2:
        if endpoint == legacy_dmx_proxy_base_url(ctx.port):
            return "enabled"
    elif endpoint == provider_proxy_base_url(ctx.port, aigw_provider_route(state)):
        return "enabled"
    if endpoint == state["direct_url"]:
        return "disabled"
    return "drifted"


def aigw_provider_route(state: Mapping[str, object]) -> str:
    """Return the provider route represented by one validated AIGW state."""
    if state.get("route_mode") != "aigw_endpoint":
        raise errors.InstallError("route state is not AIGW-managed")
    if state.get("schema_version") == 2:
        return "dmxapi"
    provider_route = state.get("provider_route")
    if not isinstance(provider_route, str) or provider_route not in PROVIDER_ROUTES:
        raise errors.InstallError("AIGW route state has no valid provider route")
    return provider_route


def set_proxy_route(ctx: installation.InstallContext, state: dict | None, *, enabled: bool) -> None:
    """Apply one authorized reversible route transition without guessing state."""
    if state is None:
        raise errors.InstallError("proxy route is unmanaged; reinstall before using control.py")
    route_mode = state.get("route_mode")
    if route_mode is None and state.get("schema_version") == 1:
        route_mode = "codex_config"
    if route_mode != "codex_config":
        raise errors.InstallError("route is AIGW-managed; use control.py with its AIGW route mode")
    status = route_status(ctx, state)
    expected = "disabled" if enabled else "enabled"
    if status == "drifted":
        raise errors.InstallError(
            "config has changed outside proxy control; refusing to overwrite it"
        )
    if status == expected:
        backup_file(ctx.codex_config)
        with open(ctx.codex_config, "r", encoding="utf-8") as fh:
            current = fh.read()
        if enabled:
            rewritten, changed = rewrite_base_url(
                current, state["source_host_substr"], state["proxy_url"]
            )
            if changed == 0 or _sha256_text(rewritten) != state["enabled_sha256"]:
                raise errors.InstallError(
                    "managed direct route no longer matches recorded install state"
                )
        else:
            try:
                with open(state["backup_path"], "r", encoding="utf-8") as fh:
                    rewritten = fh.read()
            except OSError as exc:
                raise errors.InstallError("recorded config backup is unavailable") from exc
            if _sha256_text(rewritten) != state["direct_sha256"]:
                raise errors.InstallError(
                    "recorded config backup has changed; refusing to restore it"
                )
        _atomic_write_text(ctx.codex_config, rewritten)


def backup_file(path: str) -> str:
    """Copy path -> path.bak-<n> (first free suffix). Returns the backup path."""
    n = 1
    while True:
        cand = f"{path}.bak-{n}"
        if not os.path.exists(cand):
            shutil.copy2(path, cand)
            return cand
        n += 1


def route_authority(ctx: installation.InstallContext) -> str:
    """Return the configuration authority visible at the Codex target.

    A marked AIGW provider projection remains AIGW-owned whether it is currently
    direct or loopback.  A proxy may operate an explicit ``aigw_endpoint`` mode,
    but it still delegates mutations to AIGW rather than treating that projection
    as proxy-owned configuration.
    """
    try:
        text = _read_text(ctx.codex_config)
    except OSError:
        return "unmanaged"
    start = text.find(AIGW_PROVIDER_BEGIN)
    end = text.find(AIGW_PROVIDER_END)
    if start >= 0 and end > start:
        block = text[start : end + len(AIGW_PROVIDER_END)]
        if "[model_providers.aigw]" in block and "base_url" in block:
            return "aigw"
    if load_install_state(ctx) is not None:
        return "proxy"
    return "unmanaged"
