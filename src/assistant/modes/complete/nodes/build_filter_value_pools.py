from __future__ import annotations

from typing import Callable, Any

from ..contracts import BuildFilterValuePoolsOutput
from ..state import GraphState, FilterValuePool
from ..strategy_catalog import STEP_TO_TOOL, get_strategy
from .json_io import call_llm_json


def _build_messages(
    *,
    question: str,
    planning_text: str | None,
    base: str,
    strategy_id: str,
    step_idx: int,
    call_count: int,
    turn_trace: list[dict],
    step_description: str,
    tool_name: str,
    filter_field_specs: list[dict[str, Any]],
) -> list[dict]:
    """
    LLM I/O only.
    """
    trace_lines = []
    for i, e in enumerate(turn_trace):
        trace_lines.append(
            f"{i}. tool={e.get('tool_name')} base={e.get('base')} "
            f"meaning={e.get('meaning')} params={e.get('params')} "
            f"rows_preview={e.get('results', {}).get('rows')}"
        )

    field_lines = []
    for f in filter_field_specs:
        line = f"- {f['name']}: type={f['type']}, description={f.get('description', '')}"
        if "default" in f:
            line += f", default={f['default']}"
        if "candidate_values" in f:
            line += f", candidate_values={f['candidate_values']}"
        field_lines.append(line)

    system = (
        "Build grounded candidate filter-value pools for the current step.\n"
        "Return ONLY valid JSON matching this schema:\n"
        '{ "calls": [[{"field_name": string, "values": [any, ...], "description": string}, ...], ...], "debug_reason": string }\n'
        "Valid filter fields:\n"
        + ("\n".join(field_lines) if field_lines else "(none)") + "\n"
        "Rules:\n"
        f"- Return exactly {call_count} call entries in calls.\n"
        "- Each inner list belongs to one existing call.\n"
        "- Use only listed filter fields; never invent fields.\n"
        "- Build candidate pools only; do not choose final params.\n"
        "- If no grounded useful values exist for a call, return an empty list.\n"
        "- Values must be grounded in the question, planning text, selected prior trace, or provided candidate_values.\n"
        "- If a field provides candidate_values, choose only from those values and copy them verbatim.\n"
        "- Do not shorten, normalize, or paraphrase provided string values.\n"
        "- Do not invent numeric/date/boolean values. Use numeric/date/boolean values only when explicitly stated in the question or prior trace.\n"
        "- Do not guess thresholds such as min/max values from vague words like many, high, low, recent, or strong.\n"
        "- Descriptions must state provenance: question text, planning text, prior trace, or candidate_values.\n"
    )

    user = (
        f"Question:\n{question}\n\n"
        f"Planning text:\n{planning_text or ''}\n\n"
        f"Base: {base}\n"
        f"Strategy: {strategy_id}\n"
        f"Current step_idx: {step_idx}\n"
        f"Current tool: {tool_name}\n"
        f"Step description: {step_description}\n"
        f"Existing call count: {call_count}\n\n"
        f"TurnMemory.tool_trace:\n" + ("\n".join(trace_lines) if trace_lines else "(empty)")
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _normalize_output(
    out: BuildFilterValuePoolsOutput,
    *,
    call_count: int,
) -> BuildFilterValuePoolsOutput:
    """
    Parsing/validation post-processing.
    Keep exactly call_count entries.
    """
    calls = out.calls[:call_count]
    while len(calls) < call_count:
        calls.append([])
    return BuildFilterValuePoolsOutput(calls=calls, debug_reason=out.debug_reason)


def _apply_output(state: GraphState, out: BuildFilterValuePoolsOutput) -> BuildFilterValuePoolsOutput:
    """
    Pure state mutation.

    Writes:
      - state.turn.execution.calls[*].filter_value_pools

    Does NOT create/remove calls.
    """
    for call_state, pool_list in zip(state.turn.execution.calls, out.calls):
        call_state.filter_value_pools = [
            FilterValuePool.model_validate(p.model_dump()) for p in pool_list
        ]
    return out


def build_filter_value_pools(
    state: GraphState,
    *,
    filter_field_specs: list[dict[str, Any]],
    llm: Callable[..., dict],
) -> BuildFilterValuePoolsOutput:
    """
    Reads:
      - state.turn.context.question
      - state.turn.context.planning_text
      - state.turn.context.base
      - state.turn.context.strategy_id
      - state.turn.execution.step_idx
      - state.turn.execution.calls
      - state.turn.memory.tool_trace

    Writes:
      - state.turn.execution.calls[*].filter_value_pools
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
        out = BuildFilterValuePoolsOutput(calls=[], debug_reason="no existing calls to fill")
        return _apply_output(state, out)

    step = strategy.steps[exe.step_idx]
    tool_name = STEP_TO_TOOL[step.kind]

    messages = _build_messages(
        question=ctx.question,
        planning_text=ctx.planning_text,
        base=ctx.base,
        strategy_id=ctx.strategy_id,
        step_idx=exe.step_idx,
        call_count=call_count,
        turn_trace=[e.model_dump() for e in state.turn.memory.tool_trace],
        step_description=step.description,
        tool_name=tool_name,
        filter_field_specs=filter_field_specs,
    )

    default = BuildFilterValuePoolsOutput(
        calls=[[] for _ in range(call_count)],
        debug_reason="model output invalid; using empty filter pools",
    )

    out = call_llm_json(
        llm,
        messages=messages,
        output_model=BuildFilterValuePoolsOutput,
        default=default,
    )

    out = _normalize_output(out, call_count=call_count)
    return _apply_output(state, out)