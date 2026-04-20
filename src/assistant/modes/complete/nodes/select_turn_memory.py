from __future__ import annotations

from typing import Callable, List

from ..state import GraphState, TraceEntry
from ..contracts import SelectTurnMemoryOutput
from .json_io import call_llm_json


def _build_messages(question: str, planning_text: str | None, tool_trace: list[dict]) -> list[dict]:
    """
    LLM I/O only (no state access).
    """
    lines: List[str] = []
    for i, e in enumerate(tool_trace):
        lines.append(
            f"{i}. tool={e.get('tool_name')} base={e.get('base')} params={e.get('params')} "
            f"meaning={e.get('meaning')} rows_total={e.get('results', {}).get('rows_total')}"
        )

    system = (
        "You select a SMALL subset of prior executed tool trace entries to help answer the current question.\n"
        "Selection is for PLANNING and CONTEXT CARRYOVER, not only for already-complete answers.\n"
        "Return ONLY one JSON object:\n"
        '{ "selected_trace_indexes": [int, ...], "debug_reason": string }\n'
        "Selection objective:\n"
        "- Pick entries that reduce uncertainty for the next steps: they should provide reusable evidence, constraints, or candidate values.\n"
        "Guidelines:\n"
        "- Partial usefulness is valid: if an entry supports part of the needed analysis, include it even if it does not fully answer the question.\n"
        "- When the current question implies multiple slices (e.g., comparing two segments), include any existing slice evidence you have; missing slices can be computed later.\n"
        "- Prefer entries that define the current focus entity or slice (e.g., which channel/company/base/threshold was used) over generic or unrelated entries.\n"
        "- Prefer entries that contain concrete examples (IDs/URLs/locations/titles) when the question asks for examples.\n"
        "- Prefer entries that contain ranked/aggregated context (grouped results) when the question depends on a 'leading' item from prior analysis.\n"
        "- Consistency: avoid selecting near-duplicates that differ only by a constraint value (e.g., min_locations, seed)\n"
        "  unless the question explicitly requires comparing those constraints.\n"
        "- Prefer more recent entries when multiple candidates satisfy the above.\n"
        "- Keep the selection small (usually 1–4 entries). If nothing is useful, return [].\n"
        "- Do not invent entries.\n"
    )

    user = (
        f"Question:\n{question}\n\n"
        f"Planning text (optional):\n{planning_text or ''}\n\n"
        "Session tool_trace entries:\n" + "\n".join(lines)
    )

    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _apply_output(state: GraphState, out: SelectTurnMemoryOutput) -> SelectTurnMemoryOutput:
    """
    Pure state mutation.
    Writes:
      - state.turn.memory.tool_trace
    """
    full = state.session.tool_trace
    chosen: list[TraceEntry] = []
    seen = set()

    for i in out.selected_trace_indexes:
        if isinstance(i, int) and 0 <= i < len(full) and i not in seen:
            chosen.append(full[i])
            seen.add(i)

    state.turn.memory.tool_trace = chosen
    return SelectTurnMemoryOutput(selected_trace_indexes=list(seen), debug_reason=out.debug_reason)


def select_turn_memory(
    state: GraphState,
    *,
    llm: Callable[..., dict],
) -> SelectTurnMemoryOutput:
    """
    Reads:
      - state.turn.context.question
      - state.turn.context.planning_text
      - state.session.tool_trace

    Writes:
      - state.turn.memory.tool_trace
    """
    if state.turn is None:
        raise RuntimeError("turn not initialized (start_turn must run before select_turn_memory)")

    full = state.session.tool_trace
    if not full:
        state.turn.memory.tool_trace = []
        return SelectTurnMemoryOutput(selected_trace_indexes=[], debug_reason="empty session tool_trace")

    messages = _build_messages(
        question=state.turn.context.question,
        planning_text=state.turn.context.planning_text,
        tool_trace=[e.model_dump() for e in full],
    )

    default = SelectTurnMemoryOutput(selected_trace_indexes=[], debug_reason="model output invalid; selected none")
    out = call_llm_json(llm, messages=messages, output_model=SelectTurnMemoryOutput, default=default)

    return _apply_output(state, out)