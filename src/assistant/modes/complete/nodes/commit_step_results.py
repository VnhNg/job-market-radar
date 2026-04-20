from __future__ import annotations

from typing import Any, Callable

from ..contracts import CommitStepResultsOutput
from ..state import GraphState, TraceEntry
from ..strategy_catalog import STEP_TO_TOOL, get_strategy
from .json_io import call_llm_json


def _current_tool_name(state: GraphState) -> str:
    strategy_id = state.turn.context.strategy_id
    if not strategy_id:
        raise RuntimeError("strategy_id not set")

    spec = get_strategy(strategy_id)
    step_idx = state.turn.execution.step_idx
    if step_idx < 0 or step_idx >= len(spec.steps):
        raise RuntimeError(f"step_idx out of range for strategy {strategy_id}: {step_idx}")

    return STEP_TO_TOOL[spec.steps[step_idx].kind]


def _successful_call_results(state: GraphState) -> list[dict[str, Any]]:
    successful: list[dict[str, Any]] = []
    for call in state.turn.execution.calls:
        if not call.results:
            continue
        params_sent = call.results.get("params_sent")
        payload = call.results.get("payload")
        if not isinstance(params_sent, dict) or not isinstance(payload, dict):
            continue
        successful.append(call.results)
    return successful


def _build_messages(
    *,
    question: str,
    planning_text: str | None,
    base: str,
    tool_name: str,
    call_results: list[dict[str, Any]],
) -> list[dict]:
    lines = []
    for i, r in enumerate(call_results):
        lines.append(
            f"{i}. payload={r.get('payload')} "
            f"latency_ms={r.get('latency_ms')} reused={r.get('reused')}"
        )

    system = (
        "Write one compact factual meaning string for each successful executed call result.\n"
        "Return ONLY one JSON object matching this schema:\n"
        '{ "meanings": [string, ...], "debug_reason": string }\n'
        "Rules:\n"
        f"- Return exactly {len(call_results)} meanings in order.\n"
        "- Each meaning must be useful as future memory for later nodes, not as a user-facing answer.\n"
        "- Describe the general meaning of the executed call: tool intent, grouping/entity scope, important filters, and whether ordering/ranking matters.\n"
        "- Prefer compact semantic labels over narrative prose.\n"
        "- If the result is a ranked breakdown, say what was ranked and keep any top entities in their result order.\n"
        "- If the result is a detail/sample call, say which entity or slice it covers and what kind of example/detail rows it contains.\n"
        "- Do not write answer-style sentences.\n"
        "- Do not invent facts not supported by params/payload.\n"
    )

    user = (
        f"Question:\n{question}\n\n"
        f"Planning text:\n{planning_text or ''}\n\n"
        f"Base: {base}\n"
        f"Tool: {tool_name}\n\n"
        f"Successful call results:\n" + "\n".join(lines)
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _default_meaning(tool_name: str, base: str, params_sent: dict[str, Any]) -> str:
    parts = [tool_name, f"base={base}"]

    for key in ("metric", "dimensions", "select", "channel", "company", "bundesland", "min_locations"):
        if key in params_sent:
            parts.append(f"{key}={params_sent[key]}")

    return " | ".join(parts)


def _normalize_output(
    out: CommitStepResultsOutput,
    *,
    tool_name: str,
    base: str,
    call_results: list[dict[str, Any]],
) -> CommitStepResultsOutput:
    meanings: list[str] = []
    raw = out.meanings[: len(call_results)]

    for i, call_result in enumerate(call_results):
        text = raw[i].strip() if i < len(raw) and isinstance(raw[i], str) else ""
        if not text:
            text = _default_meaning(tool_name, base, call_result.get("params_sent", {}))
        meanings.append(text)

    while len(meanings) < len(call_results):
        call_result = call_results[len(meanings)]
        meanings.append(_default_meaning(tool_name, base, call_result.get("params_sent", {})))

    return CommitStepResultsOutput(meanings=meanings, debug_reason=out.debug_reason)


def _memory_results_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(payload)
    for key in ("base", "select", "filters"):
        cleaned.pop(key, None)
    return cleaned


def _apply_output(
    state: GraphState,
    *,
    tool_name: str,
    base: str,
    call_results: list[dict[str, Any]],
    out: CommitStepResultsOutput,
) -> CommitStepResultsOutput:
    entries: list[TraceEntry] = []

    for call_result, meaning in zip(call_results, out.meanings):
        entry = TraceEntry(
            tool_name=tool_name,
            base=base,
            params=dict(call_result.get("params_sent", {})),
            latency_ms=call_result.get("latency_ms"),
            results=_memory_results_payload(dict(call_result.get("payload", {}))),
            meaning=meaning,
        )
        entries.append(entry)

    state.session.tool_trace.extend(entries)
    state.turn.memory.tool_trace.extend(entries)
    return out


def commit_step_results(
    state: GraphState,
    *,
    llm: Callable[..., dict],
) -> CommitStepResultsOutput:
    """
    Reads:
      - state.turn.context.question
      - state.turn.context.planning_text
      - state.turn.context.base
      - state.turn.context.strategy_id
      - state.turn.execution.step_idx
      - state.turn.execution.calls[*].results

    Writes:
      - state.session.tool_trace
      - state.turn.memory.tool_trace

    Notes:
      - only successful results are committed
      - does not increment step_idx
      - does not clear calls
    """
    if state.turn is None:
        raise RuntimeError("turn not initialized")

    base = state.turn.context.base
    if not base:
        raise RuntimeError("base not set")

    tool_name = _current_tool_name(state)
    call_results = _successful_call_results(state)

    if not call_results:
        return CommitStepResultsOutput(meanings=[], debug_reason="no successful call results to commit")

    messages = _build_messages(
        question=state.turn.context.question,
        planning_text=state.turn.context.planning_text,
        base=base,
        tool_name=tool_name,
        call_results=call_results,
    )

    default = CommitStepResultsOutput(
        meanings=[],
        debug_reason="model output invalid; using default meanings",
    )

    out = call_llm_json(
        llm,
        messages=messages,
        output_model=CommitStepResultsOutput,
        default=default,
    )

    out = _normalize_output(
        out,
        tool_name=tool_name,
        base=base,
        call_results=call_results,
    )
    return _apply_output(
        state,
        tool_name=tool_name,
        base=base,
        call_results=call_results,
        out=out,
    )