from __future__ import annotations

import time
from typing import Any

from ..state import GraphState
from ..strategy_catalog import STEP_TO_TOOL, get_strategy


def _current_tool_name(state: GraphState) -> str:
    strategy_id = state.turn.context.strategy_id
    if not strategy_id:
        raise RuntimeError("strategy_id not set")

    spec = get_strategy(strategy_id)
    step_idx = state.turn.execution.step_idx
    if step_idx < 0 or step_idx >= len(spec.steps):
        raise RuntimeError(f"step_idx out of range for strategy {strategy_id}: {step_idx}")

    return STEP_TO_TOOL[spec.steps[step_idx].kind]


def _adapt_params_for_http(planned_params: dict[str, Any], *, base: str) -> dict[str, Any]:
    """
    Inject base and adapt planner arrays -> HTTP query params.
    """
    params = dict(planned_params)
    params["base"] = base

    for key in ("dimensions", "select"):
        value = params.get(key)
        if isinstance(value, list):
            params[key] = ",".join(str(x) for x in value)

    return params


def _normalize_params_key(params: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    """
    Stable key for reuse lookup.
    """
    return tuple(sorted(params.items(), key=lambda kv: kv[0]))


def _find_reusable_result(
    state: GraphState,
    *,
    tool_name: str,
    base: str,
    params_sent: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Look only in TurnMemory.tool_trace (not full session memory).
    Reuse if tool/base/normalized params match exactly.
    """
    target_key = _normalize_params_key(params_sent)

    for entry in reversed(state.turn.memory.tool_trace):
        if entry.tool_name != tool_name:
            continue
        if entry.base != base:
            continue
        if _normalize_params_key(entry.params) != target_key:
            continue

        return {
            "params_sent": dict(entry.params),
            "payload": dict(entry.results),
            "latency_ms": 0,
            "reused": True,
        }

    return None


def _execute_one(
    *,
    tool_runtime,
    tool_name: str,
    params_sent: dict[str, Any],
    max_rows_to_llm: int,
    max_chars_to_llm: int,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    _full, llm_payload = tool_runtime.call_for_llm(
        tool_name,
        params_sent,
        max_rows=max_rows_to_llm,
        max_chars=max_chars_to_llm,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    return {
        "params_sent": dict(params_sent),
        "payload": dict(llm_payload),
        "latency_ms": latency_ms,
        "reused": False,
    }


def _apply_results(state: GraphState, results_by_call: list[dict[str, Any]]) -> None:
    """
    Writes:
      - state.turn.execution.calls[*].results
    """
    for call_state, result in zip(state.turn.execution.calls, results_by_call):
        call_state.results = dict(result)


def execute_step_calls(
    state: GraphState,
    *,
    tool_runtime,
    max_rows_to_llm: int,
    max_chars_to_llm: int,
) -> None:
    """
    Reads:
      - state.turn.context.base
      - state.turn.context.strategy_id
      - state.turn.execution.step_idx
      - state.turn.execution.calls[*].planned_params
      - state.turn.memory.tool_trace

    Writes:
      - state.turn.execution.calls[*].results

    Notes:
      - derives tool from strategy_id + step_idx
      - injects base
      - adapts arrays -> CSV
      - reuses identical prior result from TurnMemory when possible
    """
    if state.turn is None:
        raise RuntimeError("turn not initialized")

    base = state.turn.context.base
    if not base:
        raise RuntimeError("base not set")

    tool_name = _current_tool_name(state)

    results_by_call: list[dict[str, Any]] = []

    for call_state in state.turn.execution.calls:
        planned = dict(call_state.planned_params)

        if not planned:
            results_by_call.append({})
            continue

        params_sent = _adapt_params_for_http(planned, base=base)

        reused = _find_reusable_result(
            state,
            tool_name=tool_name,
            base=base,
            params_sent=params_sent,
        )
        if reused is not None:
            results_by_call.append(reused)
            continue

        executed = _execute_one(
            tool_runtime=tool_runtime,
            tool_name=tool_name,
            params_sent=params_sent,
            max_rows_to_llm=max_rows_to_llm,
            max_chars_to_llm=max_chars_to_llm,
        )
        results_by_call.append(executed)

    _apply_results(state, results_by_call)