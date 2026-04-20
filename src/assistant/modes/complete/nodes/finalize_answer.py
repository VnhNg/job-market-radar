from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from ..state import GraphState
from .json_io import call_llm_json


class _FinalizeAnswerOutput(BaseModel):
    """
    JSON-only LLM output for the final answer.
    """
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(default="")
    debug_reason: str = ""


def _build_messages(
    *,
    question: str,
    planning_text: str | None,
    turn_trace: list[dict],
) -> list[dict]:
    """
    LLM I/O only.
    """
    trace_lines = []
    for i, e in enumerate(turn_trace):
        trace_lines.append(
            f"{i}. tool={e.get('tool_name')} base={e.get('base')} "
            f"meaning={e.get('meaning')} params={e.get('params')} "
            f"results={e.get('results')}"
        )

    system = (
        "Write the final answer grounded strictly in the provided trace entries.\n"
        "Return ONLY one JSON object matching this schema:\n"
        '{ "answer": string, "debug_reason": string }\n'
        "Rules:\n"
        "- Use only evidence from the provided trace entries.\n"
        "- Include a short 'Sources' section at the end as bullet lines.\n"
        "- Each source line should summarize tool + key params/results briefly.\n"
        "- Do not invent facts not supported by the trace.\n"
        "- Be concise but complete.\n"
    )

    user = (
        f"Question:\n{question}\n\n"
        f"Planning text:\n{planning_text or ''}\n\n"
        f"TurnMemory.tool_trace:\n" + ("\n".join(trace_lines) if trace_lines else "(empty)")
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def finalize_answer(
    state: GraphState,
    *,
    llm: Callable[..., dict],
) -> str:
    """
    Reads:
      - state.turn.context.question
      - state.turn.context.planning_text
      - state.turn.memory.tool_trace

    Writes:
      - nothing

    Returns:
      - final grounded answer string
    """
    if state.turn is None:
        raise RuntimeError("turn not initialized")

    messages = _build_messages(
        question=state.turn.context.question,
        planning_text=state.turn.context.planning_text,
        turn_trace=[e.model_dump() for e in state.turn.memory.tool_trace],
    )

    default = _FinalizeAnswerOutput(
        answer="I couldn't produce a grounded answer from the available trace entries.",
        debug_reason="model output invalid; used fallback answer",
    )

    out = call_llm_json(
        llm,
        messages=messages,
        output_model=_FinalizeAnswerOutput,
        default=default,
    )

    answer = out.answer.strip()
    if not answer:
        answer = default.answer
    return answer