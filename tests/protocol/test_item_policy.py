"""Response item policy closure contracts."""

from __future__ import annotations

import pytest

from codex_responses_proxy.protocol.input_variant import diagnose
from codex_responses_proxy.protocol.item_policy import ProjectionStrategy
from codex_responses_proxy.protocol.item_policy import classify_item
from codex_responses_proxy.protocol.item_policy import item_types


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
        ("additional_tools", ProjectionStrategy.DROP_AUXILIARY),
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


@pytest.mark.parametrize("value", [None, "future_item", 1, {}])
def test_unknown_or_invalid_item_has_no_policy(value: object) -> None:
    assert classify_item(value) is None
