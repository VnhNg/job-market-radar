from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ToolKind = Literal["breakdown", "detail", "none"]


@dataclass(frozen=True)
class ToolPolicy:
    """
    Static governance metadata per tool.
    This is NOT derived from OpenAPI. It's our product policy:
    - how tools should be used by the agent
    - which parameter "shape" they follow
    """
    kind: ToolKind
    requires_base: bool
    # parameters that define the core "shape" of the tool call (plus base if required)
    core_params: frozenset[str]


_TOOL_POLICIES: dict[str, ToolPolicy] = {
    "analytics_breakdown": ToolPolicy(
        kind="breakdown",
        requires_base=True,
        core_params=frozenset({"base", "metric", "dimensions", "limit", "dry_run"}),
    ),
    "analytics_detail": ToolPolicy(
        kind="detail",
        requires_base=True,
        core_params=frozenset({"base", "select", "limit", "dry_run"}),
    ),
    "analytics_sample": ToolPolicy(
        kind="detail",
        requires_base=True,
        core_params=frozenset({"base", "select", "limit", "dry_run", "seed"}),
    ),
    "analytics_semantic_spec": ToolPolicy(
        kind="none",
        requires_base=False,
        core_params=frozenset(),
    ),
    "definitions": ToolPolicy(
        kind="none",
        requires_base=False,
        core_params=frozenset(),
    ),
}


def get_tool_policy(tool_name: str) -> ToolPolicy:
    """
    Fail-closed policy lookup: if a tool isn't configured here,
    we refuse to run it via the agent.
    """
    pol = _TOOL_POLICIES.get(tool_name)
    if not pol:
        raise KeyError(f"No ToolPolicy configured for tool: {tool_name}")
    return pol
