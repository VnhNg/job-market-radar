from __future__ import annotations

from typing import List
from ...state import (
    CallState,
    GraphState,
    ExecutionState,
)
from ...strategy_catalog import STEP_TO_TOOL, get_strategy


def current_strategy(state: GraphState):
    if state.turn is None:
        raise RuntimeError("turn not initialized")
    strategy_id = state.turn.context.strategy_id
    if not strategy_id:
        raise RuntimeError("strategy_id not set")
    return get_strategy(strategy_id)


def current_step_spec(state: GraphState):
    """
    Read-only helper for the current strategy step.
    """
    strategy = current_strategy(state)
    step_idx = state.turn.execution.step_idx
    if step_idx < 0 or step_idx >= len(strategy.steps):
        raise RuntimeError(f"step_idx out of range for strategy {strategy.id}: {step_idx}")
    return strategy.steps[step_idx]


def current_tool_name(state: GraphState) -> str:
    """
    Read-only helper for the current step tool.
    """
    step = current_step_spec(state)
    return STEP_TO_TOOL[step.kind]


def has_next_step(state: GraphState) -> bool:
    """
    Whether there is another step after the current one.
    """
    strategy = current_strategy(state)
    return (state.turn.execution.step_idx + 1) < len(strategy.steps)


def prepare_next_step(state: GraphState) -> None:
    """
    Deterministically advance to the next step and reset per-step call state.

    Requires:
      - current step already committed

    Writes:
      - state.turn.execution.step_idx += 1
      - state.turn.execution.calls reset to fresh CallState list

    Notes:
      - multi_step strategies always reset to exactly 1 call
      - single_step strategies reuse calls_in_step from TurnContext
    """
    if state.turn is None:
        raise RuntimeError("turn not initialized")

    strategy = current_strategy(state)
    next_step_idx = state.turn.execution.step_idx + 1
    if next_step_idx >= len(strategy.steps):
        raise RuntimeError("no next step available")

    if strategy.mode.value == "multi_step":
        next_call_count = 1
    else:
        calls_in_step = state.turn.context.calls_in_step
        if calls_in_step is None or calls_in_step < 1:
            raise RuntimeError("calls_in_step not set")
        next_call_count = calls_in_step

    state.turn.execution = ExecutionState(
        step_idx=next_step_idx,
        calls=[CallState() for _ in range(next_call_count)],
    )


def should_finalize(state: GraphState) -> bool:
    """
    Deterministic loop decision after commit_step_results.
    """
    return not has_next_step(state)

