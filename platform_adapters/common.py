"""common — shared helpers for the installer and platform adapters.

Holds the InstallContext (all resolved absolute paths + config), the Codex
config.toml locator/rewriter, and the cross-platform Python-interpreter resolver.
Stdlib only.
"""

from __future__ import annotations

import os
import re
import sys
import shutil
import subprocess
import json
import hashlib
import shutil
import tempfile
import urllib.parse
from dataclasses import dataclass, field


LABEL = "com.user.codex-dmx-watchdog"   # launchd/systemd/task identifier
DEFAULT_PORT = 8791
DEFAULT_UPSTREAM = "https://www.dmxapi.cn"
DEFAULT_PROXY_LOG_MAX_BYTES = 4 * 1024 * 1024
DEFAULT_PROXY_LOG_BACKUP_COUNT = 3
DEFAULT_WATCHDOG_LOG_MAX_BYTES = 512 * 1024
DEFAULT_WATCHDOG_LOG_BACKUP_COUNT = 2
INSTALL_DIRNAME = os.path.join(".codex", "dmx-proxy")   # under $HOME
STATE_FILENAME = "install-state.json"
STATE_SCHEMA_VERSION = 2
PAYLOAD_MANIFEST_FILENAME = "payload-manifest.json"
PAYLOAD_MANIFEST_SCHEMA_VERSION = 1
AUXILIARY_STATE_FILES = (STATE_FILENAME,)
AIGW_PROVIDER_BEGIN = "# >>> AIGW managed provider >>>"
AIGW_PROVIDER_END = "# <<< AIGW managed provider <<<"
RUNTIME_PAYLOAD_FILES = (
    "VERSION",
    "control.py",
    "governance.py",
    "platform_adapters/__init__.py",
    "platform_adapters/common.py",
    "platform_adapters/linux.py",
    "platform_adapters/macos.py",
    "platform_adapters/windows.py",
    "proxy/dmx_responses_proxy.py",
    "watchdog/watchdog.py",
)


class UnsupportedPlatform(RuntimeError):
    pass


class InstallError(RuntimeError):
    pass


class ManualStartRequired(RuntimeError):
    """Non-fatal: files placed and watchdog started for this session, but no
    boot-persistence hook could be installed (no systemd bus, no crontab). The
    installer reports this as a warning, not a failure."""
    pass


@dataclass
class InstallContext:
    """Everything the adapters need, resolved to absolute paths at install time."""
    home: str
    install_dir: str          # ~/.codex/dmx-proxy
    proxy_script: str         # <install_dir>/proxy/dmx_responses_proxy.py
    watchdog_script: str      # <install_dir>/watchdog/watchdog.py
    python: str               # ABSOLUTE interpreter path (never bare "python3")
    codex_config: str         # ~/.codex/config.toml
    log_dir: str              # ~/.codex/log
    port: int = DEFAULT_PORT
    upstream: str = DEFAULT_UPSTREAM
    proxy_log_max_bytes: int = DEFAULT_PROXY_LOG_MAX_BYTES
    proxy_log_backup_count: int = DEFAULT_PROXY_LOG_BACKUP_COUNT
    watchdog_log_max_bytes: int = DEFAULT_WATCHDOG_LOG_MAX_BYTES
    watchdog_log_backup_count: int = DEFAULT_WATCHDOG_LOG_BACKUP_COUNT
    env: dict = field(default_factory=dict)


def home_dir() -> str:
    return os.path.expanduser("~")


def codex_home() -> str:
    """Codex root: $CODEX_HOME or ~/.codex (same convention on all three OSes)."""
    return os.environ.get("CODEX_HOME", os.path.join(home_dir(), ".codex"))


def codex_config_path() -> str:
    return os.path.join(codex_home(), "config.toml")


def resolve_python() -> str:
    """Return an ABSOLUTE python interpreter path safe for a service context.

    A service (launchd/systemd/Task Scheduler) runs with a minimal PATH that does
    NOT include Homebrew/pyenv/venv shims, so a bare ``python3`` will not resolve.
    We record an absolute path at install time.

    Order:
      1. sys.executable — the interpreter running the installer (most reliable).
      2. Windows: the ``py`` launcher (``py -3``) resolved to its real exe, since
         the bare ``python.exe`` on PATH is often the 0-byte WindowsApps Store stub.
      3. shutil.which fallbacks.
    """
    exe = sys.executable
    if exe and os.path.isabs(exe) and os.path.exists(exe):
        # Guard against the Windows Store stub (0-byte redirector under WindowsApps).
        if not _is_windows_store_stub(exe):
            return exe

    if os.name == "nt":
        # Ask the py launcher for the real interpreter path.
        for launcher in ("py", "py.exe"):
            found = shutil.which(launcher)
            if found:
                try:
                    out = subprocess.check_output(
                        [found, "-3", "-c", "import sys;print(sys.executable)"],
                        text=True, stderr=subprocess.DEVNULL,
                    ).strip()
                    if out and os.path.exists(out) and not _is_windows_store_stub(out):
                        return out
                except Exception:
                    pass
        for name in ("python.exe", "python3.exe", "python"):
            found = shutil.which(name)
            if found and not _is_windows_store_stub(found):
                return found
    else:
        for name in ("python3", "python"):
            found = shutil.which(name)
            if found:
                return found

    if exe:
        return exe
    raise InstallError("could not resolve an absolute python interpreter path")


def _is_windows_store_stub(path: str) -> bool:
    """The Microsoft Store app-execution-alias stub is a ~0-byte file under
    ...\\WindowsApps\\ that opens the Store instead of running Python."""
    if os.name != "nt":
        return False
    if "windowsapps" in path.lower():
        try:
            return os.path.getsize(path) < 1024
        except OSError:
            return True
    return False


def windows_pythonw(python_exe: str) -> str:
    """Return the matching ``pythonw.exe`` for a resolved ``python.exe`` so the
    watchdog runs without a console window flashing at logon. Falls back to the
    console exe if the windowless variant is absent."""
    if os.name != "nt":
        return python_exe
    cand = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
    return cand if os.path.exists(cand) else python_exe


# ---------------------------------------------------------------------------
# Codex config.toml — locate and (TOML-aware, minimally) rewrite base_url.
# ---------------------------------------------------------------------------

_BASEURL_RE = re.compile(
    r'^(?P<indent>\s*)base_url\s*=\s*(?P<q>["\'])(?P<url>.*?)(?P=q)\s*(?P<comment>#.*)?$'
)


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
        body = line[:-len(ending)] if ending else line
        m = _BASEURL_RE.match(body)
        if m and old_host_substr in m.group("url") and m.group("url") != new_base_url:
            q = m.group("q")
            comment = m.group("comment") or ""
            out_lines.append(
                f'{m.group("indent")}base_url = {q}{new_base_url}{q}'
                + (f" {comment}" if comment else "") + ending
            )
            changed += 1
        else:
            out_lines.append(line)
    return "".join(out_lines), changed


def proxy_base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/v1"


def validate_port(port: int) -> int:
    """Accept only a real TCP port before it reaches service definitions."""
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise InstallError("port must be an integer in 1..65535")
    return port


def validate_log_retention(value: int, *, name: str, minimum: int, maximum: int) -> int:
    """Accept one bounded runtime-log retention setting for service rendering."""
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise InstallError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def normalize_upstream_url(value: str) -> str:
    """Validate a service-safe remote HTTP(S) upstream URL.

    The value is propagated into shell-adjacent Windows and service definitions;
    reject whitespace, control characters and quote-like metacharacters rather
    than relying on each platform renderer to repair unsafe input.
    """
    if not isinstance(value, str) or not value:
        raise InstallError("upstream must be a non-empty HTTP(S) URL")
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise InstallError("upstream URL cannot contain whitespace or control characters")
    if any(character in value for character in ('"', "'", "%", "!", "^", "&", "|", "<", ">", "`", "$", "\\", "(", ")", ";")):
        raise InstallError("upstream URL contains unsafe characters")
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise InstallError("upstream must be an absolute HTTP(S) URL with a hostname")
        if parsed.username is not None or parsed.password is not None:
            raise InstallError("upstream URL cannot include user credentials")
        if parsed.query or parsed.fragment:
            raise InstallError("upstream URL cannot include a query or fragment")
        if parsed.path and not parsed.path.startswith("/"):
            raise InstallError("upstream URL path must be absolute")
        port = parsed.port  # validates an explicit numeric port in range
        if port == 0:
            raise InstallError("upstream URL port must be in 1..65535")
    except ValueError as exc:
        raise InstallError("upstream URL has an invalid port") from exc
    return value.rstrip("/")


def install_state_path(ctx: InstallContext) -> str:
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


def payload_transaction_dir(ctx: InstallContext) -> str:
    """Return the sibling directory used for short-lived payload transactions."""
    return f"{ctx.install_dir}.transaction"


def _payload_source_paths(root: str) -> list[str]:
    missing = [relative for relative in RUNTIME_PAYLOAD_FILES if not os.path.isfile(os.path.join(root, relative))]
    if missing:
        raise InstallError("source payload is incomplete: " + ", ".join(missing))
    return list(RUNTIME_PAYLOAD_FILES)


def stage_payload_transaction(ctx: InstallContext, source_root: str) -> str:
    """Prepare a complete payload beside the live install without changing it.

    Only the declared re-creatable runtime files enter the stage.  User/runtime
    state stays in the live directory until commit, so a failed staging check
    cannot destroy route ownership, logs, or install state.
    """
    stage_parent = payload_transaction_dir(ctx)
    if os.path.lexists(stage_parent):
        raise InstallError(f"payload transaction path already exists: {stage_parent}")
    os.makedirs(os.path.dirname(stage_parent), exist_ok=True)
    try:
        os.makedirs(stage_parent, mode=0o700)
        stage = tempfile.mkdtemp(prefix="payload-", dir=stage_parent)
        for relative in _payload_source_paths(source_root):
            source = os.path.join(source_root, relative)
            target = os.path.join(stage, relative)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
        staged = InstallContext(
            home=ctx.home,
            install_dir=stage,
            proxy_script=os.path.join(stage, "proxy", "dmx_responses_proxy.py"),
            watchdog_script=os.path.join(stage, "watchdog", "watchdog.py"),
            python=ctx.python,
            codex_config=ctx.codex_config,
            log_dir=ctx.log_dir,
            port=ctx.port,
            upstream=ctx.upstream,
            proxy_log_max_bytes=ctx.proxy_log_max_bytes,
            proxy_log_backup_count=ctx.proxy_log_backup_count,
            watchdog_log_max_bytes=ctx.watchdog_log_max_bytes,
            watchdog_log_backup_count=ctx.watchdog_log_backup_count,
            env=dict(ctx.env),
        )
        write_payload_manifest(staged)
        ok, detail = verify_payload_manifest(staged)
        if not ok:
            raise InstallError(f"staged payload integrity check failed: {detail}")
        return stage
    except Exception:
        shutil.rmtree(stage_parent, ignore_errors=True)
        raise


def commit_payload_transaction(ctx: InstallContext, stage: str) -> None:
    """Atomically replace declared payload files while preserving user state.

    A complete validated stage is copied into a sibling rollback directory first.
    The live directory's route state, logs, and unknown files are untouched.
    If any declared payload write or final manifest verification fails, the
    previous declared payload is restored before the failure is returned.
    """
    transaction_root = payload_transaction_dir(ctx)
    stage = os.path.abspath(stage)
    transaction_root = os.path.abspath(transaction_root)
    if not stage.startswith(transaction_root + os.sep) or not os.path.isdir(stage):
        raise InstallError("payload stage is outside the controlled transaction directory")
    staged = InstallContext(
        home=ctx.home,
        install_dir=stage,
        proxy_script=os.path.join(stage, "proxy", "dmx_responses_proxy.py"),
        watchdog_script=os.path.join(stage, "watchdog", "watchdog.py"),
        python=ctx.python,
        codex_config=ctx.codex_config,
        log_dir=ctx.log_dir,
        port=ctx.port,
        upstream=ctx.upstream,
        proxy_log_max_bytes=ctx.proxy_log_max_bytes,
        proxy_log_backup_count=ctx.proxy_log_backup_count,
        watchdog_log_max_bytes=ctx.watchdog_log_max_bytes,
        watchdog_log_backup_count=ctx.watchdog_log_backup_count,
        env=dict(ctx.env),
    )
    ok, detail = verify_payload_manifest(staged)
    if not ok:
        raise InstallError(f"refusing unverified staged payload: {detail}")
    rollback = os.path.join(transaction_root, "rollback")
    if os.path.lexists(rollback):
        raise InstallError(f"payload rollback path already exists: {rollback}")
    try:
        os.makedirs(rollback, mode=0o700)
        for relative in RUNTIME_PAYLOAD_FILES + (PAYLOAD_MANIFEST_FILENAME,):
            source = os.path.join(ctx.install_dir, relative)
            if not os.path.isfile(source):
                raise InstallError(f"live payload is incomplete before commit: {relative}")
            target = os.path.join(rollback, relative)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
        for relative in RUNTIME_PAYLOAD_FILES + (PAYLOAD_MANIFEST_FILENAME,):
            source = os.path.join(stage, relative)
            target = os.path.join(ctx.install_dir, relative)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
        ok, detail = verify_payload_manifest(ctx)
        if not ok:
            raise InstallError(f"committed payload integrity check failed: {detail}")
    except Exception as exc:
        try:
            restore_payload_transaction(ctx)
        except Exception as rollback_exc:
            raise InstallError(f"payload commit failed and rollback failed: {rollback_exc}") from exc
        raise


def restore_payload_transaction(ctx: InstallContext) -> None:
    """Restore the declared payload held by the active transaction rollback."""
    rollback = os.path.join(payload_transaction_dir(ctx), "rollback")
    if not os.path.isdir(rollback):
        raise InstallError("payload rollback is unavailable")
    for relative in RUNTIME_PAYLOAD_FILES + (PAYLOAD_MANIFEST_FILENAME,):
        source = os.path.join(rollback, relative)
        target = os.path.join(ctx.install_dir, relative)
        if not os.path.isfile(source):
            raise InstallError(f"payload rollback is incomplete: {relative}")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
    ok, detail = verify_payload_manifest(ctx)
    if not ok:
        raise InstallError(f"restored payload integrity check failed: {detail}")


def finalize_payload_transaction(ctx: InstallContext) -> None:
    """Remove the short-lived staged payload and rollback only after success."""
    shutil.rmtree(payload_transaction_dir(ctx), ignore_errors=True)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_install_state(
    ctx: InstallContext,
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
        "proxy_url": proxy_base_url(ctx.port),
        "source_host_substr": source_host_substr,
        "direct_sha256": _sha256_text(direct_text),
        "enabled_sha256": _sha256_text(enabled_text),
    }


def make_aigw_install_state(
    ctx: InstallContext,
    *,
    aigw_config_path: str,
    account: str,
    direct_url: str,
) -> dict:
    """Construct an AIGW-owned endpoint route record without retaining secrets."""
    if not isinstance(account, str) or not account:
        raise InstallError("AIGW account must be non-empty")
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "route_mode": "aigw_endpoint",
        "aigw_config_path": os.path.abspath(aigw_config_path),
        "aigw_account": account,
        "proxy_url": proxy_base_url(ctx.port),
        "direct_url": normalize_upstream_url(direct_url),
    }


def _valid_install_state(ctx: InstallContext, state: object) -> bool:
    if not isinstance(state, dict):
        return False
    schema_version = state.get("schema_version")
    route_mode = state.get("route_mode")
    # v1 contained only direct Codex-config state. Accept it as a read-only
    # migration shape so an installed v1.0.2 payload can still disable/uninstall
    # an earlier managed route; every newly written state uses schema v2.
    if schema_version == 1 and route_mode is None:
        route_mode = "codex_config"
    elif schema_version != STATE_SCHEMA_VERSION:
        return False
    if route_mode == "codex_config":
        if state.get("config_path") != os.path.abspath(ctx.codex_config):
            return False
        if state.get("proxy_url") != proxy_base_url(ctx.port):
            return False
        backup = state.get("backup_path")
        if not isinstance(backup, str) or not backup.startswith(os.path.abspath(ctx.codex_config) + ".bak-"):
            return False
        if not isinstance(state.get("source_host_substr"), str) or not state["source_host_substr"]:
            return False
        return all(isinstance(state.get(key), str) and len(state[key]) == 64 for key in ("direct_sha256", "enabled_sha256"))
    if route_mode == "aigw_endpoint":
        return (
            isinstance(state.get("aigw_config_path"), str)
            and os.path.isabs(state["aigw_config_path"])
            and isinstance(state.get("aigw_account"), str)
            and bool(state["aigw_account"])
            and state.get("proxy_url") == proxy_base_url(ctx.port)
            and isinstance(state.get("direct_url"), str)
            and _is_valid_upstream_url(state["direct_url"])
        )
    return False


def write_install_state(ctx: InstallContext, state: dict) -> None:
    if not _valid_install_state(ctx, state):
        raise InstallError("refusing to write invalid proxy install state")
    _atomic_write_text(install_state_path(ctx), json.dumps(state, sort_keys=True) + "\n")


def load_install_state(ctx: InstallContext) -> dict | None:
    try:
        with open(install_state_path(ctx), "r", encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    return state if _valid_install_state(ctx, state) else None


def remove_install_state(ctx: InstallContext) -> None:
    try:
        os.remove(install_state_path(ctx))
    except FileNotFoundError:
        pass


def route_status(ctx: InstallContext, state: dict | None) -> str:
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


def _is_valid_upstream_url(value: object) -> bool:
    try:
        normalize_upstream_url(value)  # type: ignore[arg-type]
    except InstallError:
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


def aigw_route_status(ctx: InstallContext, state: dict, config_path: str) -> str:
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            endpoint = aigw_endpoint(fh.read(), state["aigw_account"])
    except OSError:
        return "drifted"
    if endpoint == state["proxy_url"]:
        return "enabled"
    if endpoint == state["direct_url"]:
        return "disabled"
    return "drifted"


def set_proxy_route(ctx: InstallContext, state: dict | None, *, enabled: bool) -> None:
    if state is None:
        raise InstallError("proxy route is unmanaged; reinstall before using control.py")
    route_mode = state.get("route_mode")
    if route_mode is None and state.get("schema_version") == 1:
        route_mode = "codex_config"
    if route_mode != "codex_config":
        raise InstallError("route is AIGW-managed; use control.py with its AIGW route mode")
    status = route_status(ctx, state)
    expected = "disabled" if enabled else "enabled"
    if status == "drifted":
        raise InstallError("config has changed outside proxy control; refusing to overwrite it")
    if status == expected:
        backup_file(ctx.codex_config)
        with open(ctx.codex_config, "r", encoding="utf-8") as fh:
            current = fh.read()
        if enabled:
            rewritten, changed = rewrite_base_url(current, state["source_host_substr"], state["proxy_url"])
            if changed == 0 or _sha256_text(rewritten) != state["enabled_sha256"]:
                raise InstallError("managed direct route no longer matches recorded install state")
        else:
            try:
                with open(state["backup_path"], "r", encoding="utf-8") as fh:
                    rewritten = fh.read()
            except OSError as exc:
                raise InstallError("recorded config backup is unavailable") from exc
            if _sha256_text(rewritten) != state["direct_sha256"]:
                raise InstallError("recorded config backup has changed; refusing to restore it")
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
def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def payload_manifest_path(ctx: InstallContext) -> str:
    """Return the installed runtime payload manifest path."""
    return os.path.join(ctx.install_dir, PAYLOAD_MANIFEST_FILENAME)


def _payload_relative_paths(root: str) -> list[str]:
    """Return the declared executable payload, not arbitrary deployment residue."""
    missing = [relative for relative in RUNTIME_PAYLOAD_FILES if not os.path.isfile(os.path.join(root, relative))]
    if missing:
        raise InstallError("installed payload is incomplete: " + ", ".join(missing))
    return list(RUNTIME_PAYLOAD_FILES)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def write_payload_manifest(ctx: InstallContext) -> str:
    """Write a deterministic manifest for the installed executable payload.

    The manifest deliberately excludes configuration, backups, logs, request data,
    tokens, and installation state.  It is provenance for the re-creatable runtime
    projection, not a snapshot of user state.
    """
    files = _payload_relative_paths(ctx.install_dir)
    if not files:
        raise InstallError("installed payload is empty; refusing to write manifest")
    manifest = {
        "schema_version": PAYLOAD_MANIFEST_SCHEMA_VERSION,
        "release": _read_text(os.path.join(ctx.install_dir, "VERSION")).strip(),
        "files": {
            relative: _sha256_file(os.path.join(ctx.install_dir, relative))
            for relative in files
        },
    }
    _atomic_write_text(
        payload_manifest_path(ctx),
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    return payload_manifest_path(ctx)


def verify_payload_manifest(ctx: InstallContext) -> tuple[bool, str]:
    """Verify the installed executable projection without reading user config."""
    path = payload_manifest_path(ctx)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"manifest unavailable: {exc}"
    if not isinstance(manifest, dict) or manifest.get("schema_version") != PAYLOAD_MANIFEST_SCHEMA_VERSION:
        return False, "manifest schema is unsupported"
    release = manifest.get("release")
    files = manifest.get("files")
    if not isinstance(release, str) or not release or not isinstance(files, dict) or not files:
        return False, "manifest is incomplete"
    version_path = os.path.join(ctx.install_dir, "VERSION")
    try:
        installed_release = _read_text(version_path).strip()
    except OSError as exc:
        return False, f"installed VERSION unavailable: {exc}"
    if installed_release != release:
        return False, f"release mismatch: manifest={release} installed={installed_release}"
    expected_files = _payload_relative_paths(ctx.install_dir)
    if sorted(files) != expected_files:
        return False, "manifest file set mismatch"
    for relative, expected in files.items():
        if not isinstance(expected, str) or len(expected) != 64:
            return False, f"invalid digest: {relative}"
        path = os.path.join(ctx.install_dir, *relative.split("/"))
        try:
            actual = _sha256_file(path)
        except OSError as exc:
            return False, f"payload unavailable: {relative}: {exc}"
        if actual != expected:
            return False, f"hash mismatch: {relative}"
    return True, f"release {release}; {len(files)} files verified"


def route_authority(ctx: InstallContext) -> str:
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
        block = text[start:end + len(AIGW_PROVIDER_END)]
        if "[model_providers.aigw]" in block and "base_url" in block:
            return "aigw"
    if load_install_state(ctx) is not None:
        return "proxy"
    return "unmanaged"


def listener_pids(port: int) -> list[int]:
    """Return PIDs listening on ``port``; identity verification is separate."""
    try:
        if os.name == "nt":
            output = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, check=False,
            ).stdout
            pids = []
            for line in output.splitlines():
                fields = line.split()
                if len(fields) >= 5 and fields[1].endswith(f":{port}") and fields[3].upper() == "LISTENING":
                    try:
                        pids.append(int(fields[-1]))
                    except ValueError:
                        pass
            return pids
        output = subprocess.run(
            ["lsof", "-tiTCP:" + str(port), "-sTCP:LISTEN"], capture_output=True, text=True, check=False,
        ).stdout
        return [int(value) for value in output.split() if value.isdigit()]
    except Exception:
        return []


def process_command(pid: int) -> str:
    """Return a process command line for identity proof, or an empty string."""
    try:
        if os.name == "nt":
            command = (
                "$p=Get-CimInstance Win32_Process -Filter \"ProcessId=" + str(pid) + "\";"
                "if ($p) {$p.CommandLine}"
            )
            return subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True, text=True, check=False,
            ).stdout.strip()
        return subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=False,
        ).stdout.strip()
    except Exception:
        return ""


def verified_proxy_listener_pids(ctx: InstallContext) -> list[int]:
    """Return only listeners whose command line names this installed proxy script."""
    expected = os.path.abspath(ctx.proxy_script)
    return [
        pid for pid in listener_pids(ctx.port)
        if expected in os.path.abspath(process_command(pid))
    ]


def terminate_pid(pid: int) -> None:
    """Request termination of one already-verified listener PID."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/pid", str(pid), "/f"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        subprocess.run(["kill", "-TERM", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
