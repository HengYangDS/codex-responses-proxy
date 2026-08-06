"""Response-failed retry and pair-safe recovery contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping

from codex_responses_proxy.protocol import response_failed
from codex_responses_proxy.runtime import config as runtime_config

COMPACTION_BUDGET = runtime_config.DEFAULT_RESPONSE_FAILED_COMPACTION_BUDGET


def _body(input_items, **extra):
    return json.dumps({"input": input_items, **extra}, separators=(",", ":")).encode()


def _message(role, content):
    return {"type": "message", "role": role, "content": content}


def _call(kind, call_id, payload):
    key = "arguments" if kind == "function_call" else "input"
    name = "wait" if kind == "function_call" else "exec"
    return {"type": kind, "call_id": call_id, "name": name, key: payload}


def _output(kind, call_id, payload):
    return {"type": kind, "call_id": call_id, "output": payload}


class ResponseFailedContracts:
    def assert_rejected(self, function, fixtures, subtests):
        for raw, budget in fixtures:
            with subtests.test(raw=raw, budget=budget):
                assert function(raw, budget) == (None, None)

    def assert_compacted(self, compact: bytes | None, detail: Mapping[str, object] | None):
        """Narrow a successful compaction result for contract assertions."""
        assert compact is not None
        assert detail is not None
        return (compact, detail)

    def test_retry_disposition_classifies_gateway_and_terminal_failures(self, subtests):
        cases = (
            (429, b"rate limited", ""),
            (524, b"gateway timeout", "full"),
            (477, b'{"error":{"type":"dmx_api_error","code":"empty_response"}}', ""),
            (477, b'{"error":"unprocessable"}', ""),
            (477, b'{"error":{"type":"other_gateway","code":"empty_response"}}', ""),
            (400, b'{"error":{"type":"new_api_error","code":"response_failed"}}', "full"),
            (418, b"teapot", ""),
            (400, b"invalid_encrypted_content", ""),
            (400, b"could not be verified", ""),
            (
                400,
                b'{"error":{"message":"Request blocked. (fixture)","type":"invalid_request_error","code":"invalid_prompt"}}',
                "full",
            ),
            (400, b'{"error":{"type":"invalid_request_error","code":"invalid_payload"}}', "once"),
        )
        for status, payload, expected in cases:
            with subtests.test(status=status, payload=payload):
                assert response_failed.retry_disposition(status, payload) == expected
        assert json.loads(response_failed.exhausted_payload(4))["error"]["attempts"] == 4

    def test_recovery_is_not_triggered_by_incidental_error_prose(self) -> None:
        prose_only = b'{"error":{"message":"response_failed and request blocked are documentation text","type":"invalid_request_error","code":"ordinary_error"}}'
        assert response_failed.retry_disposition(400, prose_only) == ""

    def test_response_failed_compaction_keeps_complete_tool_pairs_and_latest_user(self):
        """Fallback removes only an old prefix; no retained output is orphaned."""
        body = _body(
            [
                _message("user", "old" + "x" * 300000),
                _call("custom_tool_call", "custom-1", "{}"),
                _output("custom_tool_call_output", "custom-1", "y" * 300000),
                _call("function_call", "function-1", "{}"),
                _output("function_call_output", "function-1", "done"),
                _message("user", "latest user context must survive"),
            ],
            prompt_cache_key="cache-key-must-not-reach-the-fallback",
        )
        compact, detail = response_failed.compact_request(body, COMPACTION_BUDGET)
        compact, detail = self.assert_compacted(compact, detail)
        assert detail["removed_inputs"] >= 1
        assert len(compact) <= COMPACTION_BUDGET
        obj = json.loads(compact)
        assert obj["store"] is False
        assert "prompt_cache_key" not in obj
        assert obj["input"][-1]["content"] == "latest user context must survive"
        calls = {
            item["call_id"]
            for item in obj["input"]
            if item.get("type") in ("custom_tool_call", "function_call")
        }
        outputs = {
            item["call_id"]
            for item in obj["input"]
            if item.get("type") in ("custom_tool_call_output", "function_call_output")
        }
        assert outputs.issubset(calls)
        assert "function-1" in calls

    def test_response_failed_compaction_never_starts_at_an_orphaned_tool_output(self):
        body = _body(
            [
                _message("user", "old" + "x" * 10000),
                _call("custom_tool_call", "custom-oversize", "{}"),
                _output("custom_tool_call_output", "custom-oversize", "y" * 600000),
                _message("user", "newest user context"),
            ]
        )
        compact, detail = response_failed.compact_request(body, COMPACTION_BUDGET)
        compact, detail = self.assert_compacted(compact, detail)
        assert detail["removed_inputs"] == 3
        obj = json.loads(compact)
        assert obj["input"] == [_message("user", "newest user context")]

    def test_response_failed_compaction_reduces_an_already_sub_budget_failure(self):
        body = _body(
            [
                _message("user", "old" + "x" * 280000),
                _message("user", "latest user context"),
                _call("custom_tool_call", "latest-call", "{}"),
                _output("custom_tool_call_output", "latest-call", "y" * 180000),
            ],
            prompt_cache_key="stale-full-history-key",
        )
        assert len(body) < COMPACTION_BUDGET
        compact, detail = response_failed.compact_request(body, COMPACTION_BUDGET)
        compact, detail = self.assert_compacted(compact, detail)
        assert len(compact) <= len(body) // 2
        assert detail["removed_inputs"] == 1
        assert "prompt_cache_key" not in json.loads(compact)

    def test_response_failed_compaction_uses_smallest_safe_suffix_when_budget_is_impossible(self):
        body = _body(
            [
                _message("user", "old context"),
                _message("user", "latest user context"),
                _call("custom_tool_call", "latest-call", "{}"),
                _output("custom_tool_call_output", "latest-call", "y" * 220000),
            ]
        )
        compact, detail = response_failed.compact_request(body, budget=20000)
        compact, detail = self.assert_compacted(compact, detail)
        assert not detail["budget_met"]
        assert len(compact) < len(body)
        obj = json.loads(compact)
        assert obj["input"][0]["content"] == "latest user context"
        assert response_failed.tool_pair_boundary_is_safe(obj["input"], 0)

    def test_response_failed_compaction_is_a_noop_when_no_safe_suffix_fits(self):
        body = _body(
            [_message("user", "newest user context")],
            tools=[{"type": "function", "name": "huge", "parameters": "x" * 600000}],
            prompt_cache_key="must-remain-on-original-request",
        )
        compact, detail = response_failed.compact_request(body, COMPACTION_BUDGET)
        assert compact is None
        assert detail is None
        assert json.loads(body)["prompt_cache_key"] == "must-remain-on-original-request"

    def test_response_failed_dialogue_recovery_keeps_latest_context_without_tool_replay(self):
        body = _body(
            [
                _message("developer", "old policy"),
                _message("user", "old request"),
                _call("custom_tool_call", "old", "{}"),
                _output("custom_tool_call_output", "old", "old result"),
                _message("developer", "current policy"),
                _message("user", "intermediate request"),
                _message("user", "latest user request"),
                _call("custom_tool_call", "new", "{}"),
                _output("custom_tool_call_output", "new", "large" + "x" * 100000),
            ],
            prompt_cache_key="stale-full-history-key",
        )
        recovery, detail = response_failed.recover_dialogue(body, COMPACTION_BUDGET)
        recovery, detail = self.assert_compacted(recovery, detail)
        recovered = json.loads(recovery)
        assert recovered["store"] is False
        assert "prompt_cache_key" not in recovered
        assert recovered["input"] == [
            _message("developer", "current policy"),
            _message("user", "latest user request"),
        ]
        assert detail["dropped_input_items"] == 7
        assert len(recovery) < len(body)

    def test_response_failed_dialogue_recovery_allows_current_user_without_instruction(self):
        body = _body(
            [
                _message("user", "old request"),
                _message("assistant", "old response"),
                _message("user", "latest user request"),
                _call("custom_tool_call", "new", "{}"),
                _output("custom_tool_call_output", "new", "large" + "x" * 100000),
            ]
        )
        recovery, detail = response_failed.recover_dialogue(body, COMPACTION_BUDGET)
        recovery, detail = self.assert_compacted(recovery, detail)
        assert json.loads(recovery)["input"] == [_message("user", "latest user request")]
        assert detail["retained_messages"] == 1

    def test_response_failed_pair_boundary_ignores_non_object_items(self):
        items: list[object] = [
            1,
            {"type": "function_call_output", "call_id": "missing", "output": "x"},
        ]
        assert not response_failed.tool_pair_boundary_is_safe(items, 0)
        assert response_failed.tool_pair_boundary_is_safe(items, 2)

    def test_response_failed_rejects_invalid_compaction_and_recovery_boundaries(self, subtests):
        common = ((b"not-json", None), (b"[]", None), (b'{"input":[]}', None))
        self.assert_rejected(
            response_failed.compact_request,
            (*common, (b'{"input":[1,2]}', None), (b'{"input":[{},{}]}', 0)),
            subtests,
        )
        valid = _body([_message("user", "old"), _message("user", "current")])
        self.assert_rejected(
            response_failed.recover_dialogue,
            (
                *common,
                (b'{"input":[{"type":"message","role":"developer","content":"x"}]}', None),
                (valid, 0),
                (valid, 1),
            ),
            subtests,
        )
