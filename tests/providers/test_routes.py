#!/usr/bin/env python3
"""Provider route isolation and common projection contracts."""

from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_responses_proxy.runtime import state  # noqa: E402
from tests.listener.proxy_fixture import request  # noqa: E402
from tests.listener.proxy_fixture import running_proxy  # noqa: E402


def _body(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


class ProviderRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        state.reset_for_test()

    def test_all_three_routes_forward_the_same_portable_body(self) -> None:
        raw = _body(
            {
                "previous_response_id": "provider-response",
                "include": ["reasoning.encrypted_content"],
                "input": [
                    {"type": "reasoning", "id": "rs_old", "encrypted_content": "opaque"},
                    {
                        "type": "message",
                        "id": "msg_old",
                        "status": "completed",
                        "role": "assistant",
                        "phase": "final_answer",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "prior answer",
                                "annotations": [],
                            },
                            {"type": "refusal", "refusal": "prior refusal"},
                        ],
                    },
                    {"type": "message", "role": "user", "content": "continue"},
                    {
                        "type": "function_call",
                        "call_id": "c1",
                        "name": "lookup",
                        "arguments": "{}",
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "c1",
                        "output": [{"type": "output_text", "text": "tool result"}],
                    },
                ],
            }
        )
        success = b'{"id":"resp_ok","status":"completed"}'

        with running_proxy([(200, success), (200, success), (200, success)]) as (port, received):
            for route in ("dmxapi", "ucloud", "aihubmix"):
                with (
                    self.subTest(route=route),
                    request(port, raw, path=f"/{route}/v1/responses") as response,
                ):
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read(), success)

        self.assertEqual(len(received), 3)
        for forwarded in received:
            payload = json.loads(forwarded)
            self.assertNotIn("previous_response_id", payload)
            self.assertEqual(payload["include"], [])
            assistant, user, call, output = payload["input"]
            self.assertEqual(
                assistant,
                {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": "prior answerprior refusal",
                },
            )
            self.assertEqual(user, {"type": "message", "role": "user", "content": "continue"})
            self.assertEqual(call["call_id"], output["call_id"])
            self.assertEqual(output["output"], [{"type": "input_text", "text": "tool result"}])

    def test_unknown_route_and_unknown_replay_shape_never_reach_upstream(self) -> None:
        with running_proxy([]) as (port, received):
            for path, body, expected_code in (
                ("/unknown/v1/responses", _body({"input": "hello"}), 404),
                (
                    "/ucloud/v1/responses",
                    _body({"input": [{"type": "future_item", "opaque": True}]}),
                    400,
                ),
            ):
                with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as raised:
                    request(port, body, path=path)
                with raised.exception as error:
                    self.assertEqual(error.code, expected_code)
            self.assertEqual(received, [])

    def test_dmx_empty_response_cooldown_does_not_block_ucloud(self) -> None:
        empty = _body(
            {
                "error": {
                    "message": "official provider returned an empty response",
                    "type": "dmx_api_error",
                    "code": "empty_response",
                }
            }
        )
        success = b'{"id":"resp_ucloud","status":"completed"}'
        body = _body({"input": [{"type": "message", "role": "user", "content": "same"}]})

        with running_proxy([(477, empty), (477, empty), (200, success)]) as (port, received):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                request(port, body, path="/dmxapi/v1/responses")
            with raised.exception as error:
                self.assertEqual(error.code, 503)
            with request(port, body, path="/ucloud/v1/responses") as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), success)

        self.assertEqual(len(received), 3)

    def test_non_dmx_http_477_is_not_given_dmx_recovery(self) -> None:
        empty = _body(
            {
                "error": {
                    "message": "official provider returned an empty response",
                    "type": "dmx_api_error",
                    "code": "empty_response",
                }
            }
        )
        body = _body({"input": [{"type": "message", "role": "user", "content": "same"}]})

        with running_proxy([(477, empty)]) as (port, received):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                request(port, body, path="/aihubmix/v1/responses")
            with raised.exception as error:
                self.assertEqual(error.code, 477)
                self.assertEqual(error.read(), empty)

        self.assertEqual(len(received), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
