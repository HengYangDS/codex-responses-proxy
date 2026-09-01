"""Single authority for Responses input item classification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final


class ProjectionStrategy(StrEnum):
    """Provider-portable disposition for one recognized item kind."""

    MESSAGE = "message"
    AGENT_MESSAGE = "agent_message"
    CALL = "call"
    OUTPUT = "output"
    COMPACTION_TRIGGER = "compaction_trigger"
    DROP_REASONING = "drop_reasoning"
    DROP_REFERENCE = "drop_reference"
    DROP_SEARCH = "drop_search"
    DROP_AUXILIARY = "drop_auxiliary"
    DROP_LOCAL_TOOL = "drop_local_tool"
    SCHEMA_DRIFT = "schema_drift"


@dataclass(frozen=True, slots=True)
class ItemPolicy:
    """Classification facts shared by diagnostics and projection."""

    projection: ProjectionStrategy
    paired_output: str | None = None
    argument_field: str | None = None

    @property
    def rejection_reason(self) -> str:
        """Return the bounded local reason for a non-portable recognized item."""
        return "schema_drift" if self.projection is ProjectionStrategy.SCHEMA_DRIFT else ""


def _policy(
    projection: ProjectionStrategy,
    *,
    paired_output: str | None = None,
    argument_field: str | None = None,
) -> ItemPolicy:
    return ItemPolicy(projection, paired_output, argument_field)


# Client-visible item kinds are derived from the installed Codex protocol
# vocabulary. A recognized kind without a safe provider-portable projection is
# rejected as schema drift rather than mislabeled as an unknown future kind.
_SCHEMA_DRIFT_TYPES = (
    "apply_patch_call",
    "apply_patch_call_output",
    "code_interpreter_call",
    "computer_call",
    "computer_call_output",
    "file_search_call",
    "local_shell_call_output",
    "mcp_approval_request",
    "mcp_approval_response",
    "mcp_call",
    "mcp_list_tools",
    "program",
    "program_output",
    "shell_call",
    "shell_call_output",
)

ITEM_POLICIES: Final = MappingProxyType(
    {
        "message": _policy(ProjectionStrategy.MESSAGE),
        "agent_message": _policy(ProjectionStrategy.AGENT_MESSAGE),
        "additional_tools": _policy(ProjectionStrategy.DROP_AUXILIARY),
        "reasoning": _policy(ProjectionStrategy.DROP_REASONING),
        "item_reference": _policy(ProjectionStrategy.DROP_REFERENCE),
        "compaction": _policy(ProjectionStrategy.DROP_REFERENCE),
        "context_compaction": _policy(ProjectionStrategy.DROP_REFERENCE),
        "web_search_call": _policy(ProjectionStrategy.DROP_SEARCH),
        "tool_search_call": _policy(
            ProjectionStrategy.DROP_SEARCH,
            paired_output="tool_search_output",
        ),
        "tool_search_output": _policy(ProjectionStrategy.DROP_SEARCH),
        "image_generation_call": _policy(ProjectionStrategy.DROP_AUXILIARY),
        "local_shell_call": _policy(
            ProjectionStrategy.DROP_LOCAL_TOOL,
            paired_output="function_call_output",
        ),
        "function_call": _policy(
            ProjectionStrategy.CALL,
            paired_output="function_call_output",
            argument_field="arguments",
        ),
        "function_call_output": _policy(ProjectionStrategy.OUTPUT),
        "custom_tool_call": _policy(
            ProjectionStrategy.CALL,
            paired_output="custom_tool_call_output",
            argument_field="input",
        ),
        "custom_tool_call_output": _policy(ProjectionStrategy.OUTPUT),
        "compaction_trigger": _policy(ProjectionStrategy.COMPACTION_TRIGGER),
    }
    | {item_type: _policy(ProjectionStrategy.SCHEMA_DRIFT) for item_type in _SCHEMA_DRIFT_TYPES}
)


def classify_item(item_type: object) -> ItemPolicy | None:
    """Return the policy for a recognized string item type."""
    return ITEM_POLICIES.get(item_type) if isinstance(item_type, str) else None


def item_type_label(item_type: object) -> str:
    """Return a content-free diagnostic label for an item type."""
    return item_type if isinstance(item_type, str) and item_type in ITEM_POLICIES else "unknown"


def item_types() -> frozenset[str]:
    """Return the recognized item kinds declared by the policy."""
    return frozenset(ITEM_POLICIES)


def paired_item_types() -> dict[str, str]:
    """Return call-to-output relationships declared by the policy."""
    return {
        item_type: policy.paired_output
        for item_type, policy in ITEM_POLICIES.items()
        if policy.paired_output is not None
    }


def output_call_types() -> dict[str, frozenset[str]]:
    """Return output-to-call relationships declared by the policy."""
    relationships: dict[str, set[str]] = {}
    for item_type, policy in ITEM_POLICIES.items():
        if policy.paired_output is not None:
            relationships.setdefault(policy.paired_output, set()).add(item_type)
    return {output: frozenset(calls) for output, calls in relationships.items()}


def call_argument_fields() -> dict[str, str]:
    """Return call argument fields declared by the policy."""
    return {
        item_type: policy.argument_field
        for item_type, policy in ITEM_POLICIES.items()
        if policy.argument_field is not None
    }
