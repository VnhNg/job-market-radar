from __future__ import annotations

from typing import List

from ...state import (
    CallState,
    GraphState,
    ExecutionState,
    Turn,
    TurnContext,
    TurnMemory,
)

def init_turn(state: GraphState) -> None:
    """
    Deterministic turn initialization.

    Writes:
      - state.turn (fresh)
    """
    state.turn = Turn(
        context=TurnContext(question=""),
        memory=TurnMemory(tool_trace=[]),
        execution=ExecutionState(step_idx=0, calls=[]),
    )


def init_execution_from_route(state: GraphState) -> None:
    """
    Deterministically initialize execution after routing.

    Requires:
      - state.turn.context.strategy_id
      - state.turn.context.calls_in_step

    Writes:
      - state.turn.execution
    """
    if state.turn is None:
        raise RuntimeError("turn not initialized")

    calls_in_step = state.turn.context.calls_in_step
    if calls_in_step is None or calls_in_step < 1:
        raise RuntimeError("calls_in_step not set")

    state.turn.execution = ExecutionState(
        step_idx=0,
        calls=[CallState() for _ in range(calls_in_step)],
    )
