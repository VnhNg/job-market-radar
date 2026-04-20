from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class InvocationContext:
    current_user_question: str
    prior_user_questions: list[str] = field(default_factory=list)
    progress_events: list[dict[str, Any]] = field(default_factory=list)
    final_answer: str | None = None
    on_progress_event: Callable[[dict[str, Any]], None] | None = None

    def add_progress_event(
        self,
        node_name: str,
        *,
        contract_output=None,
        writes=None,
    ) -> None:
        event: dict[str, Any] = {"node": node_name}

        if contract_output is not None:
            if hasattr(contract_output, "model_dump"):
                event["output"] = contract_output.model_dump()
            else:
                event["output"] = contract_output

        if writes is not None:
            event["writes"] = writes

        self.progress_events.append(event)

        if self.on_progress_event is not None:
            self.on_progress_event(event)


def trace_brief(entries, *, max_items: int = 5) -> list[dict[str, Any]]:
    out = []
    for e in entries[-max_items:]:
        out.append(
            {
                "tool_name": e.tool_name,
                "base": e.base,
                "meaning": e.meaning,
                "params": dict(e.params),
                "rows_total": e.results.get("rows_total"),
            }
        )
    return out


def call_pools_brief(calls) -> list[dict[str, Any]]:
    out = []
    for c in calls:
        out.append(
            {
                "pool_fields": [p.field_name for p in c.filter_value_pools],
                "pool_sizes": {p.field_name: len(p.values) for p in c.filter_value_pools},
            }
        )
    return out


def planned_params_brief(calls) -> list[dict[str, Any]]:
    return [dict(c.planned_params) for c in calls]


def results_brief(calls) -> list[dict[str, Any]]:
    out = []
    for c in calls:
        r = c.results or {}
        out.append(
            {
                "has_result": bool(r),
                "params_sent": dict(r.get("params_sent", {})) if isinstance(r.get("params_sent"), dict) else {},
                "rows_total": (r.get("payload") or {}).get("rows_total") if isinstance(r.get("payload"), dict) else None,
                "reused": r.get("reused"),
            }
        )
    return out


