from __future__ import annotations

from typing import Callable

from ..state import GraphState
from ..contracts import RouteBaseStrategyOutput
from ..strategy_catalog import CATALOG
from .json_io import call_llm_json


def _build_messages(
    *,
    question: str,
    planning_text: str | None,
    turn_trace: list[dict],
    tool_descriptions: dict[str, str],
    bases_docs: dict[str, object] | None = None,
) -> list[dict]:
    """
    LLM I/O only. No state mutation.
    """
    base_lines = []
    for base_name, doc in (bases_docs or {}).items():
        if isinstance(doc, dict):
            grain = doc.get("grain", "")
            good_for = doc.get("good_for", [])
        else:
            grain = getattr(doc, "grain", "")
            good_for = getattr(doc, "good_for", [])
        base_lines.append(
            f"- {base_name}: grain={grain}, good_for={good_for}"
        )

    strategy_lines = []
    for sid, spec in CATALOG.items():
        steps = " -> ".join(step.kind.value for step in spec.steps)
        line = f"- {sid}: steps={steps}, max_calls_in_step={spec.max_calls_in_step}"
        desc_lines = []
        for i, step in enumerate(spec.steps, start=1):
            if step.description:
                desc_lines.append(f"  step {i}: {step.description}")
        if desc_lines:
            line = line + "\n" + "\n".join(desc_lines)
        strategy_lines.append(line)

    tool_lines = [f"- {name}: {desc}" for name, desc in tool_descriptions.items()]

    trace_lines = []
    for i, e in enumerate(turn_trace):
        trace_lines.append(
            f"{i}. tool={e.get('tool_name')} base={e.get('base')} "
            f"meaning={e.get('meaning')} params={e.get('params')}"
        )

    system = (
        "Choose the most appropriate base and strategy_id for the current turn.\n"
        "Return ONLY one JSON object matching this schema:\n"
        '{ "base": "jobs|replication", "strategy_id": string, "calls_in_step": int, "debug_reason": string }\n'
        "Base descriptions:\n"
        + ("\n".join(base_lines) if base_lines else "(none)") + "\n"
        "Available tools:\n"
        + ("\n".join(tool_lines) if tool_lines else "(none)") + "\n"
         "Available strategies:\n"
        + ("\n".join(strategy_lines) if strategy_lines else "(none)") + "\n"
        "Rules:\n"
        "- strategy_id must be one of the listed strategy IDs.\n"
        "- Use turn trace as carryover context for follow-ups.\n"
        "- Choose the smallest sufficient strategy.\n"
        "- If the target entity or slice is already known from turn trace, prefer direct downstream strategies.\n"
        "- Return all required routing fields: base, strategy_id, calls_in_step, debug_reason.\n"
        "- Do not propose tool arguments, filters, metrics, dimensions, or columns.\n"
    )

    user = (
        f"Question:\n{question}\n\n"
        f"Planning text:\n{planning_text or ''}\n\n"
        f"TurnMemory.tool_trace:\n" + ("\n".join(trace_lines) if trace_lines else "(empty)") + "\n\n"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _apply_output(state: GraphState, out: RouteBaseStrategyOutput) -> RouteBaseStrategyOutput:
    """
    Pure state mutation.

    Writes:
      - state.turn.context.base
      - state.turn.context.strategy_id
      - state.turn.context.calls_in_step
    """
    state.turn.context.base = out.base
    state.turn.context.strategy_id = out.strategy_id
    state.turn.context.calls_in_step = out.calls_in_step
    return out


def route_base_strategy(
    state: GraphState,
    *,
    tool_descriptions: dict[str, str],
    bases_docs: dict[str, object] | None = None,
    llm: Callable[..., dict],
) -> RouteBaseStrategyOutput:
    """
    Reads:
      - state.turn.context.question
      - state.turn.context.planning_text
      - state.turn.memory.tool_trace
      - strategy catalog
      - tool descriptions

    Writes:
      - state.turn.context.base
      - state.turn.context.strategy_id
    """
    if state.turn is None:
        raise RuntimeError("turn not initialized")

    question = state.turn.context.question
    planning_text = state.turn.context.planning_text
    turn_trace = [e.model_dump() for e in state.turn.memory.tool_trace]

    messages = _build_messages(
        question=question,
        planning_text=planning_text,
        turn_trace=turn_trace,
        tool_descriptions=tool_descriptions,
        bases_docs=bases_docs,
    )

    default = RouteBaseStrategyOutput(
        base="jobs",
        strategy_id="SINGLE_BREAKDOWN",
        calls_in_step=1,
        debug_reason="model output invalid; defaulted conservatively",
    )

    out = call_llm_json(
        llm,
        messages=messages,
        output_model=RouteBaseStrategyOutput,
        default=default,
    )

    # defensive allowlist check
    spec = CATALOG.get(out.strategy_id)
    if not spec:
        out = RouteBaseStrategyOutput(
            base="jobs",
            strategy_id="SINGLE_BREAKDOWN",
            calls_in_step=1,
            debug_reason="invalid strategy_id returned; defaulted conservatively",
        )
    else:
        if spec.mode.value == "multi_step":
            out = RouteBaseStrategyOutput(
                base=out.base,
                strategy_id=out.strategy_id,
                calls_in_step=1,
                debug_reason=out.debug_reason,
            )
        else:
            calls = out.calls_in_step
            if calls < 1:
                calls = 1
            if calls > spec.max_calls_in_step:
                calls = spec.max_calls_in_step
            out = RouteBaseStrategyOutput(
                base=out.base,
                strategy_id=out.strategy_id,
                calls_in_step=calls,
                debug_reason=out.debug_reason,
            )

    return _apply_output(state, out)