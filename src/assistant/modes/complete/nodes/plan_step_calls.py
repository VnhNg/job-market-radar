from __future__ import annotations

from typing import Any, Callable

from ..contracts import StepCallsOutput
from ..state import GraphState
from ..strategy_catalog import get_strategy
from .json_io import call_llm_json


def _build_messages(
    *,
    question: str,
    planning_text: str | None,
    base: str,
    strategy_id: str,
    step_idx: int,
    step_description: str,
    call_surfaces: list[dict[str, Any]],
) -> list[dict]:
    """
    LLM I/O only.

    Each call surface is already a complete, call-local planning surface:
    - tool name
    - injected base marker
    - step description
    - parameter meanings
    - allowed low-cardinality values
    - grounded candidate filter values
    """
    system = (
        "Plan params for the current step.\n"
        "Return ONLY one JSON object matching this schema:\n"
        '{ "calls": [dict, ...], "debug_reason": string }\n'
        "Rules:\n"
        f"- Return exactly {len(call_surfaces)} call entries in order.\n"
        "- Each call entry is planned_params for the corresponding call surface.\n"
        "- Use parameter names exactly as provided in the call surface.\n"
        "- Do not include base; base is injected outside this node.\n"
        "- Prefer grounded candidate_values when present.\n"
        "- Prefer allowed_values for low-cardinality params when present.\n"
        "- dimensions/select must be ARRAYS, not CSV.\n"
        "- Do not validate or repair here; just produce the best grounded plan.\n"
    )

    user = (
        f"Question:\n{question}\n\n"
        f"Planning text:\n{planning_text or ''}\n\n"
        f"Base: {base}\n"
        f"Strategy: {strategy_id}\n"
        f"Step index: {step_idx}\n"
        f"Step description: {step_description}\n\n"
        f"Call surfaces:\n{call_surfaces}"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _normalize_output(out: StepCallsOutput, *, call_count: int) -> StepCallsOutput:
    """
    Parsing/validation post-processing.
    Keep exactly call_count dict entries.
    """
    calls: list[dict[str, Any]] = []
    for item in out.calls[:call_count]:
        calls.append(item if isinstance(item, dict) else {})

    while len(calls) < call_count:
        calls.append({})

    return StepCallsOutput(calls=calls, debug_reason=out.debug_reason)


def _apply_output(state: GraphState, out: StepCallsOutput) -> StepCallsOutput:
    """
    Pure state mutation.

    Writes:
      - state.turn.execution.calls[*].planned_params
    """
    for call_state, planned in zip(state.turn.execution.calls, out.calls):
        call_state.planned_params = dict(planned)
    return out


def plan_step_calls(
    state: GraphState,
    *,
    call_surfaces: list[dict[str, Any]],
    llm: Callable[..., dict],
) -> StepCallsOutput:
    """
    Reads:
      - state.turn.context.question
      - state.turn.context.planning_text
      - state.turn.context.base
      - state.turn.context.strategy_id
      - state.turn.execution.step_idx
      - state.turn.execution.calls
      - current step description (from strategy catalog)
      - call_surfaces (provided by controller/runtime)

    Writes:
      - state.turn.execution.calls[*].planned_params
    """
    if state.turn is None:
        raise RuntimeError("turn not initialized")

    ctx = state.turn.context
    exe = state.turn.execution

    if not ctx.base:
        raise RuntimeError("base not set")
    if not ctx.strategy_id:
        raise RuntimeError("strategy_id not set")

    strategy = get_strategy(ctx.strategy_id)
    if exe.step_idx < 0 or exe.step_idx >= len(strategy.steps):
        raise RuntimeError(f"step_idx out of range for strategy {ctx.strategy_id}: {exe.step_idx}")

    call_count = len(exe.calls)
    if call_count == 0:
        out = StepCallsOutput(calls=[], debug_reason="no existing calls to plan")
        return _apply_output(state, out)

    step = strategy.steps[exe.step_idx]

    messages = _build_messages(
        question=ctx.question,
        planning_text=ctx.planning_text,
        base=ctx.base,
        strategy_id=ctx.strategy_id,
        step_idx=exe.step_idx,
        step_description=step.description,
        call_surfaces=call_surfaces,
    )

    default = StepCallsOutput(
        calls=[{} for _ in range(call_count)],
        debug_reason="model output invalid; using empty planned params",
    )

    out = call_llm_json(
        llm,
        messages=messages,
        output_model=StepCallsOutput,
        default=default,
    )

    out = _normalize_output(out, call_count=call_count)
    return _apply_output(state, out)