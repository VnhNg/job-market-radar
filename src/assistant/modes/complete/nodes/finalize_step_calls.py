from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from ..state import GraphState
from ..strategy_catalog import STEP_TO_TOOL, get_strategy
from .json_io import call_llm_json


class _RepairCallOutput(BaseModel):
    """
    JSON-only LLM output for one repaired call.
    """
    model_config = ConfigDict(extra="forbid")

    planned_params: dict[str, Any] = Field(default_factory=dict)
    debug_reason: str = ""


class FinalizeCallSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    initial_params: dict[str, Any] = Field(default_factory=dict)
    final_params: dict[str, Any] = Field(default_factory=dict)

    status: str = ""
    repairs_attempted: int = 0

    first_error_category: str = ""
    first_error_message: str = ""

    final_error_category: str = ""
    final_error_message: str = ""


class FinalizeStepCallsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calls: list[FinalizeCallSummary] = Field(default_factory=list)


def _current_tool_name(state: GraphState) -> str:
    strategy_id = state.turn.context.strategy_id
    if not strategy_id:
        raise RuntimeError("strategy_id not set")

    spec = get_strategy(strategy_id)
    step_idx = state.turn.execution.step_idx
    if step_idx < 0 or step_idx >= len(spec.steps):
        raise RuntimeError(f"step_idx out of range for strategy {strategy_id}: {step_idx}")

    return STEP_TO_TOOL[spec.steps[step_idx].kind]


def _build_repair_messages(
    *,
    question: str,
    planning_text: str | None,
    base: str,
    tool_name: str,
    call_surface: dict[str, Any],
    current_params: dict[str, Any],
    error_category: str,
    error_message: str,
) -> list[dict]:
    """
    LLM I/O only.
    """
    system = (
        "Fix the planned params for one tool call.\n"
        "Return ONLY one JSON object matching this schema:\n"
        '{ "planned_params": dict, "debug_reason": string }\n'
        "Rules:\n"
        "- Use only parameter names from the provided call surface.\n"
        "- Do not include base; base is injected outside this node.\n"
        "- Prefer grounded candidate_values when present.\n"
        "- Prefer allowed_values for low-cardinality params when present.\n"
        "- dimensions/select must remain ARRAYS, not CSV.\n"
        "- Fix only what is necessary to make the params valid.\n"
    )

    user = (
        f"Question:\n{question}\n\n"
        f"Planning text:\n{planning_text or ''}\n\n"
        f"Base: {base}\n"
        f"Tool: {tool_name}\n\n"
        f"Current params:\n{current_params}\n\n"
        f"Validation error category: {error_category}\n"
        f"Validation error message: {error_message}\n\n"
        f"Call surface:\n{call_surface}"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _adapt_params_for_validation(planned_params: dict[str, Any], *, base: str) -> dict[str, Any]:
    """
    Convert planner-shaped params into runtime validation shape.
    Keeps this adaptation internal to finalize_step_calls.
    """
    args = dict(planned_params)
    args["base"] = base

    for key in ("dimensions", "select"):
        value = args.get(key)
        if isinstance(value, list):
            args[key] = ",".join(str(x) for x in value)

    return args


def _validate_one_call(
    *,
    tool_runtime,
    semantic_spec,
    tool_name: str,
    base: str,
    planned_params: dict[str, Any],
) -> tuple[bool, str, str]:
    """
    Internal validation only.

    Returns:
      (ok, error_category, error_message)

    Note:
      - validate against runtime/HTTP shape
      - do not mutate planner-shaped params
    """
    validation_args = _adapt_params_for_validation(planned_params, base=base)

    try:
        validated = tool_runtime.validate_types(
            tool_name,
            base=base,
            semantic_spec=semantic_spec,
            args=validation_args,
        )
    except Exception as e:
        return False, "type", str(e)

    try:
        tool_runtime.validate_semantics(
            tool_name,
            base=base,
            semantic_spec=semantic_spec,
            args=validated,
        )
    except Exception as e:
        return False, "semantic", str(e)

    return True, "", ""


def _finalize_one_call(
    *,
    llm: Callable[..., dict],
    tool_runtime,
    semantic_spec,
    question: str,
    planning_text: str | None,
    base: str,
    tool_name: str,
    call_surface: dict[str, Any],
    planned_params: dict[str, Any],
    max_repairs: int,
) -> tuple[dict[str, Any], FinalizeCallSummary]:
    """
    Validate -> bounded repair loop -> return finalized params + compact summary.
    Fail-closed to {} if still invalid after repair budget.
    """
    initial = dict(planned_params)
    current = dict(planned_params)

    ok, error_category, error_message = _validate_one_call(
        tool_runtime=tool_runtime,
        semantic_spec=semantic_spec,
        tool_name=tool_name,
        base=base,
        planned_params=current,
    )
    if ok:
        return current, FinalizeCallSummary(
            initial_params=initial,
            final_params=dict(current),
            status="valid_initial",
            repairs_attempted=0,
        )

    first_error_category = error_category
    first_error_message = error_message
    repairs_attempted = 0

    for _ in range(max_repairs):
        repairs_attempted += 1

        default = _RepairCallOutput(
            planned_params=current,
            debug_reason="model output invalid; kept previous params",
        )

        out = call_llm_json(
            llm,
            messages=_build_repair_messages(
                question=question,
                planning_text=planning_text,
                base=base,
                tool_name=tool_name,
                call_surface=call_surface,
                current_params=current,
                error_category=error_category,
                error_message=error_message,
            ),
            output_model=_RepairCallOutput,
            default=default,
        )

        current = dict(out.planned_params)

        ok, error_category, error_message = _validate_one_call(
            tool_runtime=tool_runtime,
            semantic_spec=semantic_spec,
            tool_name=tool_name,
            base=base,
            planned_params=current,
        )
        if ok:
            return current, FinalizeCallSummary(
                initial_params=initial,
                final_params=dict(current),
                status="repaired",
                repairs_attempted=repairs_attempted,
                first_error_category=first_error_category,
                first_error_message=first_error_message,
            )

    return {}, FinalizeCallSummary(
        initial_params=initial,
        final_params={},
        status="failed_closed",
        repairs_attempted=repairs_attempted,
        first_error_category=first_error_category,
        first_error_message=first_error_message,
        final_error_category=error_category,
        final_error_message=error_message,
    )


def _apply_output(state: GraphState, finalized_params_list: list[dict[str, Any]]) -> None:
    """
    Pure state mutation.

    Writes:
      - state.turn.execution.calls[*].planned_params
    """
    for call_state, finalized in zip(state.turn.execution.calls, finalized_params_list):
        call_state.planned_params = dict(finalized)


def finalize_step_calls(
    state: GraphState,
    *,
    call_surfaces: list[dict[str, Any]],
    tool_runtime,
    semantic_spec,
    llm: Callable[..., dict],
    max_repairs: int,
) -> FinalizeStepCallsSummary:
    """
    Reads:
      - state.turn.context.question
      - state.turn.context.planning_text
      - state.turn.context.base
      - state.turn.context.strategy_id
      - state.turn.execution.step_idx
      - state.turn.execution.calls[*].planned_params
      - call_surfaces

    Writes:
      - state.turn.execution.calls[*].planned_params

    Returns:
      - compact debug summary for each call
    """
    if state.turn is None:
        raise RuntimeError("turn not initialized")

    ctx = state.turn.context
    exe = state.turn.execution

    if not ctx.base:
        raise RuntimeError("base not set")
    if not ctx.strategy_id:
        raise RuntimeError("strategy_id not set")

    tool_name = _current_tool_name(state)

    finalized_params_list: list[dict[str, Any]] = []
    summaries: list[FinalizeCallSummary] = []

    for i, call_state in enumerate(exe.calls):
        call_surface = call_surfaces[i] if i < len(call_surfaces) else {}
        finalized, summary = _finalize_one_call(
            llm=llm,
            tool_runtime=tool_runtime,
            semantic_spec=semantic_spec,
            question=ctx.question,
            planning_text=ctx.planning_text,
            base=ctx.base,
            tool_name=tool_name,
            call_surface=call_surface,
            planned_params=call_state.planned_params,
            max_repairs=max_repairs,
        )
        finalized_params_list.append(finalized)
        summaries.append(summary)

    _apply_output(state, finalized_params_list)
    return FinalizeStepCallsSummary(calls=summaries)