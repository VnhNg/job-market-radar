from __future__ import annotations

from typing import Callable, List

from ..state import GraphState
from ..contracts import StartTurnOutput
from .json_io import call_llm_json


def _build_messages(user_question: str, recent_user_questions: List[str]) -> list[dict]:
    """
    Builds system/user messages only (no state access).
    """
    n = len(recent_user_questions)

    system = (
        "Task: pick prior user questions that are relevant to the current question and write planning_text.\n"
        "Return ONLY one JSON object matching this schema:\n"
        '{ "selected_prior_indexes": [int, ...], "planning_text": string|null, "debug_reason": string }\n'
        "Rules:\n"
        f"- selected_prior_indexes refer to the provided prior questions list (0..{max(n-1,0)}).\n"
        "- If none are relevant, return [].\n"
        "- planning_text should help later planning; keep it short.\n"
        "- If you cannot rewrite a clear planning_text, then set planning_text to the raw selected questions (in order), "
        "one per line.\n"
    )

    prior_block = "\n".join([f"{i}. {q}" for i, q in enumerate(recent_user_questions)])
    user = (
        f"Current question:\n{user_question}\n\n"
        f"Prior user questions (most recent last):\n{prior_block}\n"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _apply_output(
    state: GraphState,
    user_question: str,
    out: StartTurnOutput,
    recent_user_questions: List[str],
) -> StartTurnOutput:
    """
    Pure state mutation.

    Writes:
      - state.turn.context.question
      - state.turn.context.planning_text
    """
    state.turn.context.question = user_question

    planning_text = out.planning_text.strip() if isinstance(out.planning_text, str) else ""

    # deterministic fallback: if indexes selected but no planning_text,
    # use raw selected questions, one per line
    if not planning_text:
        lines = [user_question]
        for i in out.selected_prior_indexes:
            if isinstance(i, int) and 0 <= i < len(recent_user_questions):
                lines.append(recent_user_questions[i])
        planning_text = "\n".join(line for line in lines if line)

    state.turn.context.planning_text = planning_text or None

    return StartTurnOutput(
        selected_prior_indexes=out.selected_prior_indexes,
        planning_text=state.turn.context.planning_text,
        debug_reason=out.debug_reason,
    )


def start_turn(
    state: GraphState,
    *,
    user_question: str,
    recent_user_questions: List[str],
    llm: Callable[..., dict],
) -> StartTurnOutput:
    """
    Reads:
      - user_question
      - recent_user_questions (already bounded by controller)

    Writes:
      - state.turn.context.question
      - state.turn.context.planning_text

    Requires:
      - controller has already initialized state.turn
    """
    if state.turn is None:
        raise RuntimeError("turn not initialized (controller must create Turn before start_turn)")

    if not recent_user_questions:
        out = StartTurnOutput(
            selected_prior_indexes=[],
            planning_text=user_question,
            debug_reason="no prior user questions provided; planning_text set from current question",
        )
        return _apply_output(state, user_question, out, recent_user_questions)

    messages = _build_messages(user_question, recent_user_questions)

    default = StartTurnOutput(
        selected_prior_indexes=[],
        planning_text=None,
        debug_reason="model output invalid; skipped planning_text",
    )

    out = call_llm_json(
        llm,
        messages=messages,
        output_model=StartTurnOutput,
        default=default,
    )

    return _apply_output(state, user_question, out, recent_user_questions)