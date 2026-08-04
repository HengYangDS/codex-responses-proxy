"""Verify and transactionally install one signed native release asset."""

from __future__ import annotations

from pathlib import Path

from codex_responses_proxy.lifecycle import artifact
from codex_responses_proxy.lifecycle import context as runtime_context
from codex_responses_proxy.lifecycle import transaction
from codex_responses_proxy.lifecycle.deployment import apply
from codex_responses_proxy.relay import config as runtime_config


def build_context(
    port: int,
    *,
    proxy_log_max_bytes: int = runtime_config.DEFAULT_PROXY_LOG_MAX_BYTES,
    proxy_log_backup_count: int = runtime_config.DEFAULT_PROXY_LOG_BACKUP_COUNT,
    watchdog_log_max_bytes: int = runtime_config.DEFAULT_WATCHDOG_LOG_MAX_BYTES,
    watchdog_log_backup_count: int = runtime_config.DEFAULT_WATCHDOG_LOG_BACKUP_COUNT,
) -> runtime_context.RuntimeContext:
    """Project user-facing arguments into one portable deployment context."""

    return runtime_context.create(
        port=port,
        proxy_log_max_bytes=proxy_log_max_bytes,
        proxy_log_backup_count=proxy_log_backup_count,
        watchdog_log_max_bytes=watchdog_log_max_bytes,
        watchdog_log_backup_count=watchdog_log_backup_count,
    )


def install_asset(
    asset: Path,
    *,
    trust_anchor: Path,
    port: int = runtime_config.DEFAULT_PORT,
    timeout_seconds: float = 30.0,
) -> dict[str, object]:
    """Install one verified native asset through the platform service adapter."""

    from codex_responses_proxy.lifecycle.supervision import native_service

    ctx = build_context(port)
    released = artifact.admit(asset, trust_anchor=trust_anchor)
    payload_transaction = transaction.begin_transaction(ctx, released)
    return apply.install(
        ctx,
        payload_transaction,
        adapter=native_service.adapter(),
        runtime_reader=apply.read_runtime,
        timeout_seconds=timeout_seconds,
    )
