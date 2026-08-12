"""Shared state and transport fixtures for relay exchange contracts."""

from __future__ import annotations

from contextlib import ExitStack

import io
import json
import tempfile
import urllib.error
from email.message import Message
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import cast

from codex_responses_proxy.relay import admission, cooldown, operational_log, telemetry
from codex_responses_proxy.service import entrypoint as proxy

EXACT_ERROR = json.dumps(
    {
        "error": {
            "message": (
                "invalid request body: Invalid 'input': value did not match any expected variant"
            ),
            "type": "invalid_request_error",
            "param": "",
            "code": "validation_error",
        }
    },
    separators=(",", ":"),
).encode()


def request_body(*, stream: bool = False, secret: str = "private-current-prompt") -> bytes:
    """Return a current-turn request carrying removable provider bindings."""
    return json.dumps(
        {
            "model": "gpt-5.6-terra",
            "stream": stream,
            "instructions": "top-level-current-policy",
            "previous_response_id": "stale-response-binding",
            "conversation": {"id": "stale-conversation-binding"},
            "prompt_cache_key": "stale-private-cache-key",
            "include": ["reasoning.encrypted_content", "other"],
            "input": [
                {"type": "message", "role": "developer", "content": "current policy"},
                {"type": "message", "role": "user", "content": secret},
                {
                    "type": "custom_tool_call",
                    "call_id": "stale-call",
                    "name": "exec",
                    "input": "{}",
                },
            ],
        },
        separators=(",", ":"),
    ).encode()


class MemoryHandler(BaseHTTPRequestHandler):
    """Small handler surface for direct transport branch contracts."""

    def __init__(self, body: bytes = b"", *, path: str = "/dmxapi/v1/responses") -> None:
        self.path = path
        self.headers = Message()
        self.headers["Content-Length"] = str(len(body))
        self.headers["Connection"] = "close"
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.statuses: list[int] = []
        self.sent_headers: list[tuple[str, str]] = []

    def send_response(self, code: int, message: str | None = None) -> None:
        del message
        self.statuses.append(code)

    def send_header(self, keyword: str, value: str) -> None:
        self.sent_headers.append((keyword, value))

    def end_headers(self) -> None:
        pass

    def output(self) -> bytes:
        """Return the bytes written through the in-memory response stream."""
        return cast("io.BytesIO", self.wfile).getvalue()


def http_error(code: int, message: str, body: bytes) -> urllib.error.HTTPError:
    """Return an HTTP error with the stdlib header contract."""
    return urllib.error.HTTPError(
        "https://upstream.test/v1/responses", code, message, Message(), io.BytesIO(body)
    )


class DirectResponse:
    """Scripted response supporting normal reads and read exceptions."""

    def __init__(
        self,
        *reads: bytes | BaseException,
        content_type: str = "application/json",
        status: int = 200,
        fp: object | None = None,
    ) -> None:
        self._reads = list(reads)
        self.headers = {"Content-Type": content_type, "Content-Length": "opaque"}
        self.status = status
        self.fp = fp if fp is not None else object()

    def read(self, amount: int = -1) -> bytes:
        del amount
        item = self._reads.pop(0) if self._reads else b""
        if isinstance(item, BaseException):
            raise item
        return item

    def close(self) -> None:
        """Satisfy the upstream response lifecycle contract."""


class InputTransportFixture:
    """Reset shared relay state around each transport contract."""

    def setup_method(self) -> None:
        self._cleanups = ExitStack()
        old_log_path = operational_log.LOG_PATH
        self._log_directory = tempfile.TemporaryDirectory()
        operational_log.LOG_PATH = str(Path(self._log_directory.name) / "proxy.log")
        self._cleanups.callback(self._log_directory.cleanup)
        self._cleanups.callback(setattr, operational_log, "LOG_PATH", old_log_path)
        admission.reset_for_test()
        telemetry.reset_for_test()
        cooldown.reset_for_test()

    def teardown_method(self) -> None:
        self._cleanups.close()

    @staticmethod
    def _status_snapshot() -> dict[str, object]:
        return proxy.runtime_status()

    @classmethod
    def _status_maps(cls) -> tuple[dict[str, int], dict[str, int]]:
        status = cls._status_snapshot()
        counters = cast("dict[str, int]", status["counters"])
        classifications = cast("dict[str, int]", status["upstream_classifications"])
        return counters, classifications
