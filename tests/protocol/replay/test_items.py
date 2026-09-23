"""Response item policy closure contracts."""

from __future__ import annotations

import json

import pytest

from codex_responses_proxy.protocol.recovery.execution import tool_pair_boundary_is_safe
from codex_responses_proxy.protocol.recovery.input import diagnose
from codex_responses_proxy.protocol.replay.items import ITEM_POLICIES
from codex_responses_proxy.protocol.replay.items import ProjectionStrategy
from codex_responses_proxy.protocol.replay.items import ToolRelationships
from codex_responses_proxy.protocol.replay.items import classify_item
from codex_responses_proxy.protocol.replay.items import item_types
from codex_responses_proxy.protocol.replay.projection import sanitize_responses_body


@pytest.mark.parametrize("item_type", item_types())
def test_every_policy_item_is_diagnosed_as_recognized(item_type: str) -> None:
    diagnostic = diagnose(f'{{"input":[{{"type":"{item_type}"}}]}}'.encode())

    assert diagnostic.first_incompatible_reason != "unknown_item_type"


def test_recognized_unimplemented_standard_item_is_schema_drift() -> None:
    policy = classify_item("shell_call")

    assert policy is not None
    assert policy.projection is ProjectionStrategy.SCHEMA_DRIFT
    assert policy.rejection_reason == "schema_drift"


@pytest.mark.parametrize(
    ("item_type", "strategy"),
    [
        ("context_compaction", ProjectionStrategy.DROP_REFERENCE),
        ("image_generation_call", ProjectionStrategy.DROP_AUXILIARY),
        ("local_shell_call", ProjectionStrategy.DROP_LOCAL_TOOL),
    ],
)
def test_current_codex_auxiliary_items_have_portable_dispositions(
    item_type: str,
    strategy: ProjectionStrategy,
) -> None:
    policy = classify_item(item_type)

    assert policy is not None
    assert policy.projection is strategy
    assert policy.rejection_reason == ""


def test_current_turn_tool_catalog_is_not_auxiliary_replay_history() -> None:
    policy = classify_item("additional_tools")

    assert policy is not None
    assert policy.projection is ProjectionStrategy.TOOL_CATALOG


@pytest.mark.parametrize("value", [None, "future_item", 1, {}])
def test_unknown_or_invalid_item_has_no_policy(value: object) -> None:
    assert classify_item(value) is None


@pytest.mark.parametrize("call_type", ["function_call", "custom_tool_call"])
@pytest.mark.parametrize(
    ("sequence", "valid"),
    [
        (("call", "output"), True),
        (("call",), True),
        (("output",), False),
        (("call", "call", "output"), False),
        (("call", "output", "output"), False),
        (("call", "wrong-output"), False),
        (("call", "missing-id"), False),
    ],
)
def test_projection_diagnosis_and_recovery_share_tool_relationships(
    call_type: str, sequence: tuple[str, ...], *, valid: bool
) -> None:
    policy = classify_item(call_type)
    assert policy is not None
    assert policy.argument_field is not None
    call = {"type": call_type, "call_id": "tool", "name": "fixture", policy.argument_field: "{}"}
    output = {"type": policy.paired_output, "call_id": "tool", "output": "result"}
    other_type = "custom_tool_call" if call_type == "function_call" else "function_call"
    other = classify_item(other_type)
    assert other is not None
    fixtures = {
        "call": call,
        "output": output,
        "wrong-output": {**output, "type": other.paired_output},
        "missing-id": {**output, "call_id": ""},
    }
    items = [fixtures[name] for name in sequence]
    raw = json.dumps({"input": items}).encode()

    assert (sanitize_responses_body(raw).body is not None) is valid
    assert (diagnose(raw).first_incompatible_reason == "") is valid
    assert tool_pair_boundary_is_safe(items, 0) is valid


@pytest.mark.parametrize(
    ("call_type", "output_type"),
    [
        (kind, policy.paired_output)
        for kind, policy in ITEM_POLICIES.items()
        if policy.paired_output
    ],
)
def test_declared_tool_relationship_owns_identity_and_diagnostics(
    call_type: str, output_type: str
) -> None:
    relationships = ToolRelationships()

    assert relationships.observe(call_type, "tool") == ""
    assert relationships.call_type("tool") == call_type
    assert relationships.has_pending_call(call_type)
    assert relationships.diagnostic_flags == {"unmatched_calls"}
    assert relationships.observe(output_type, "tool") == ""
    assert not relationships.has_pending_call(call_type)
    assert relationships.diagnostic_flags == {"matched_pairs"}


def test_first_call_identity_survives_a_conflicting_replay() -> None:
    relationships = ToolRelationships()

    assert relationships.observe("function_call", "tool") == ""
    assert relationships.observe("custom_tool_call", "tool") == "duplicate_call"
    assert relationships.call_type("tool") == "function_call"
    assert relationships.observe("function_call_output", "tool") == ""
    assert relationships.diagnostic_flags == {"duplicate_calls", "matched_pairs"}


@pytest.mark.parametrize("call_type", ["function_call", "custom_tool_call"])
def test_named_distinct_deliveries_share_projection_diagnosis_and_recovery(call_type: str) -> None:
    policy = classify_item(call_type)
    assert policy is not None
    assert policy.argument_field is not None
    items = [
        {"type": call_type, "call_id": "job", "name": "run", policy.argument_field: "{}"},
        {"type": policy.paired_output, "call_id": "job", "id": "first", "output": "Running"},
        {
            "type": policy.paired_output,
            "call_id": "job",
            "id": "next",
            "name": "run",
            "output": "Complete",
        },
    ]
    raw = json.dumps({"input": items}).encode()

    assert sanitize_responses_body(raw).body is not None
    diagnostic = diagnose(raw)
    assert diagnostic.first_incompatible_reason == ""
    assert not diagnostic.duplicate_outputs
    assert tool_pair_boundary_is_safe(items, 0)
    assert not tool_pair_boundary_is_safe(items, 1)


@pytest.mark.parametrize(
    "replacement",
    [{"id": "first"}, {"id": ""}, {"id": None}, {"name": "other"}, {"name": None}],
)
def test_repeated_outputs_need_distinct_identity_and_matching_name(replacement) -> None:
    items = [
        {"type": "custom_tool_call", "call_id": "job", "name": "run", "input": "{}"},
        {"type": "custom_tool_call_output", "call_id": "job", "id": "first", "output": "A"},
        {
            "type": "custom_tool_call_output",
            "call_id": "job",
            "id": "next",
            "name": "run",
            "output": "B",
            **replacement,
        },
    ]

    result = sanitize_responses_body(json.dumps({"input": items}).encode())

    assert result.body is None
    assert result.diagnostic() == "rejected duplicate_output"


def test_delivery_identity_cannot_be_reused_as_another_calls_first_result() -> None:
    items = [
        {"type": "custom_tool_call", "call_id": "a", "name": "run", "input": "{}"},
        {"type": "custom_tool_call_output", "call_id": "a", "output": "Running"},
        {
            "type": "custom_tool_call_output",
            "call_id": "a",
            "id": "delivery",
            "name": "run",
            "output": "Done",
        },
        {"type": "custom_tool_call", "call_id": "b", "name": "run", "input": "{}"},
        {"type": "custom_tool_call_output", "call_id": "b", "id": "delivery", "output": "Other"},
    ]

    result = sanitize_responses_body(json.dumps({"input": items}).encode())

    assert result.body is None
    assert result.diagnostic() == "rejected duplicate_output"
    assert not tool_pair_boundary_is_safe(items, 0)
