from __future__ import annotations

from typing import Any

from ...state import GraphState
from ...strategy_catalog import STEP_TO_TOOL, get_strategy
from src.assistant.core.param_specs import get_operation_doc


def build_routing_base_docs(*, semantic_spec) -> dict[str, dict[str, object]]:
    """
    Focused base descriptions for router only.
    Expose only what route_base_strategy needs:
      - grain
      - good_for
    """
    out: dict[str, dict[str, object]] = {}
    for base_name, doc in semantic_spec.bases.items():
        out[base_name] = {
            "grain": doc.grain,
            "good_for": list(doc.good_for),
        }
    return out


def build_routing_tool_descriptions(*, openapi: dict, tools) -> dict[str, str]:
    """
    Source-backed tool descriptions for router only.

    Priority:
    1. x-job-market-llm-description
    2. description
    3. summary
    4. tool.title
    """
    out: dict[str, str] = {}
    for tool in tools:
        doc = get_operation_doc(openapi, tool.endpoint, tool.method)
        out[tool.name] = (
            doc.get("x-job-market-llm-description")
            or doc.get("description")
            or doc.get("summary")
            or tool.title
        )
    return out


def build_pool_builder_filter_field_specs(
    state: GraphState,
    *,
    tool_runtime,
    semantic_spec,
    filter_values_fetcher,
    distinct_limit: int = 200,
    max_full_values: int = 50,
) -> list[dict[str, Any]]:
    """
    Filter-field specs for pool builder.

    Reuses the current valid filter roster and, for low-card string fields,
    attaches backend-backed candidate_values directly.
    """
    if state.turn is None:
        raise RuntimeError("turn not initialized")

    _tool_name, base, _step_description, _planner_params = build_current_planner_param_specs(
        state,
        tool_runtime=tool_runtime,
        semantic_spec=semantic_spec,
    )

    field_specs = build_current_filter_field_specs(
        state,
        tool_runtime=tool_runtime,
        semantic_spec=semantic_spec,
    )

    out: list[dict[str, Any]] = []
    for spec in field_specs:
        item = dict(spec)

        if item.get("type") == "string":
            field_name = item["name"]
            payload = filter_values_fetcher(
                base=base,
                field=field_name,
                limit=distinct_limit,
            )
            values = payload.get("values", [])
            if isinstance(values, list) and 0 < len(values) <= max_full_values:
                item["candidate_values"] = values

        out.append(item)

    return out


def _planner_parameters_block(planner_schema_partial: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    """
    Extract JSON-schema properties + required set from the cached planner surface.
    """
    fn = planner_schema_partial.get("function", {})
    params = fn.get("parameters", {})
    properties = params.get("properties", {}) or {}
    required = set(params.get("required", []) or [])
    return properties, required


def _param_type_label(prop: dict[str, Any]) -> str:
    """
    Human-readable type string from the planner-facing JSON schema property.
    """
    t = prop.get("type")
    if t == "array":
        item_type = (prop.get("items") or {}).get("type", "any")
        return f"array[{item_type}]"
    return str(t or "any")


def _allowed_values_from_prop(prop: dict[str, Any]) -> list[Any] | None:
    """
    Read low-cardinality allowlists already attached by ToolRuntime planner surface.
    Handles both scalar enums and array item enums.
    """
    if "enum" in prop and isinstance(prop["enum"], list):
        return list(prop["enum"])

    if prop.get("type") == "array":
        items = prop.get("items") or {}
        if isinstance(items.get("enum"), list):
            return list(items["enum"])

    return None


def _candidate_specs_by_field(call_state) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for pool in call_state.filter_value_pools:
        out[pool.field_name] = {
            "values": list(pool.values),
            "description": pool.description,
        }
    return out


def build_current_planner_param_specs(
    state: GraphState,
    *,
    tool_runtime,
    semantic_spec,
) -> tuple[str, str, str, list[dict[str, Any]]]:
    """
    Deterministically expose planner-facing param metadata for the current (tool, base).

    Returns:
      - tool_name
      - base
      - step_description
      - params metadata list
    """
    if state.turn is None:
        raise RuntimeError("turn not initialized")

    base = state.turn.context.base
    strategy_id = state.turn.context.strategy_id
    if not base:
        raise RuntimeError("base not set")
    if not strategy_id:
        raise RuntimeError("strategy_id not set")

    strategy = get_strategy(strategy_id)
    step_idx = state.turn.execution.step_idx
    if step_idx < 0 or step_idx >= len(strategy.steps):
        raise RuntimeError(f"step_idx out of range for strategy {strategy_id}: {step_idx}")

    step = strategy.steps[step_idx]
    tool_name = STEP_TO_TOOL[step.kind]

    planner_schema_partial = tool_runtime.planner_schema_partial(
        tool_name,
        base=base,
        semantic_spec=semantic_spec,
    )
    properties, required = _planner_parameters_block(planner_schema_partial)

    params_out: list[dict[str, Any]] = []
    for name, prop in properties.items():
        item: dict[str, Any] = {
            "name": name,
            "type": _param_type_label(prop),
            "required": name in required,
            "description": prop.get("description", ""),
        }

        if "default" in prop:
            item["default"] = prop["default"]

        allowed_values = _allowed_values_from_prop(prop)
        if allowed_values:
            item["allowed_values"] = allowed_values

        params_out.append(item)

    return tool_name, base, step.description, params_out


def build_call_surfaces(
    state: GraphState,
    *,
    tool_runtime,
    semantic_spec,
) -> list[dict[str, Any]]:
    """
    Deterministically build one enriched call-local planning surface per existing CallState.
    """
    tool_name, base, step_description, planner_params = build_current_planner_param_specs(
        state,
        tool_runtime=tool_runtime,
        semantic_spec=semantic_spec,
    )

    surfaces: list[dict[str, Any]] = []

    for call_state in state.turn.execution.calls:
        candidate_specs = _candidate_specs_by_field(call_state)

        params_out: list[dict[str, Any]] = []
        for param in planner_params:
            item = dict(param)

            name = item["name"]
            spec = candidate_specs.get(name)
            if spec and spec.get("values"):
                item["candidate_values"] = spec["values"]
                if spec.get("description"):
                    item["candidate_description"] = spec["description"]

            params_out.append(item)

        surfaces.append(
            {
                "tool_name": tool_name,
                "base": {"value": base, "injected": True},
                "step_description": step_description,
                "parameters": params_out,
            }
        )

    return surfaces


def build_current_filter_field_specs(
    state: GraphState,
    *,
    tool_runtime,
    semantic_spec,
) -> list[dict[str, Any]]:
    """
    Deterministically expose only valid filter-field metadata for the current (tool, base).
    Reuses the same planner-facing param metadata as build_call_surfaces(...).
    """
    _tool_name, _base, _step_description, planner_params = build_current_planner_param_specs(
        state,
        tool_runtime=tool_runtime,
        semantic_spec=semantic_spec,
    )

    _FILTER_ONLY_EXCLUDED_NAMES = {
        "metric",
        "dimensions",
        "select",
        "limit",
        "seed",
        "dry_run",
    }
    out: list[dict[str, Any]] = []
    for param in planner_params:
        if param["name"] in _FILTER_ONLY_EXCLUDED_NAMES:
            continue
        out.append(dict(param))

    return out