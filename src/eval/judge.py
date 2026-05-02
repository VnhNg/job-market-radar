# src/eval/judge.py
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.assistant.core.ollama_client import ollama_chat
from src.assistant.core.registry import load_assistant_config
from src.assistant.core.semantic_spec import fetch_semantic_spec, SemanticSpec
from src.assistant.modes.complete.strategy_catalog import CATALOG


EvalStatus = Literal["pass", "fail", "error"]


class EvalJudgeCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    target_user_text: str = Field(min_length=1)
    prior_user_questions: list[str] = Field(default_factory=list)
    progress_events: list[dict[str, Any]]
    final_answer: str


class EvalJudgeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    status: EvalStatus
    first_failed_node: str | None = None
    reason: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)

    def to_failure_json(self) -> dict[str, Any]:
        if self.status == "pass":
            return {}
        return {
            "first_failed_node": self.first_failed_node,
            "reason": self.reason,
            "details": self.details,
        }


class EvalJudgeBatchDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[EvalJudgeDecision]


JUDGE_SYSTEM_PROMPT = """
You judge traces from a graph-based analytics agent.

Goal:
- Decide pass/fail/error for each case.
- If failed, identify the first node that made the run materially wrong.
- Judge backward from the final answer, then report the earliest responsible node.

Use only the provided semantic_spec, strategy_catalog, progress_events, and final_answer.
Do not invent business semantics.

Node roles:
start_turn = interpret the user turn.
select_turn_memory = select relevant prior tool trace for follow-ups.
route_base_strategy = choose semantic base and strategy.
init_execution = initialize calls for the chosen strategy.
build_filter_value_pools = ground candidate filter values.
plan_step_calls = choose tool params.
finalize_step_calls = validate/repair params.
execute_step_calls = execute tools.
commit_step_results = store useful evidence/meaning.
prepare_next_step = move through multi-step strategy.
finalize_answer = answer grounded in committed/executed evidence.

Return raw JSON only:
{
  "decisions": [
    {
      "case_id": "same input case_id",
      "status": "pass|fail|error",
      "first_failed_node": null,
      "reason": "short reason",
      "details": {}
    }
  ]
}

Rules:
- One decision per case.
- If status is pass, first_failed_node must be null.
- If status is fail/error, first_failed_node must be a graph node name or "run_turn" or "llm_judge".
- Do not wrap JSON in Markdown.
"""


def semantic_payload(spec: SemanticSpec) -> dict[str, Any]:
    return {
        "breakdown": {
            base: {
                "metrics": base_spec.metrics,
                "dimensions": base_spec.dimensions,
                "filters": list(base_spec.filters.keys()),
            }
            for base, base_spec in spec.breakdown.items()
        },
        "detail": {
            base: {
                "columns": base_spec.columns,
                "filters": list(base_spec.filters.keys()),
            }
            for base, base_spec in spec.detail.items()
        },
    }


def strategy_catalog_payload() -> dict[str, Any]:
    return {
        strategy_id: {
            "mode": strategy.mode.value,
            "steps": [step.kind.value for step in strategy.steps],
            "max_calls_in_step": strategy.max_calls_in_step,
        }
        for strategy_id, strategy in CATALOG.items()
    }


def judge_runs_batch(*, cases: list[EvalJudgeCase]) -> EvalJudgeBatchDecision:
    if not cases:
        return EvalJudgeBatchDecision(decisions=[])

    cfg = load_assistant_config()
    semantic_spec = fetch_semantic_spec(
        str(cfg.api.base_url),
        timeout_sec=cfg.agent.request_timeout_sec,
    )

    judge_input = {
        "semantic_spec": semantic_payload(semantic_spec),
        "strategy_catalog": strategy_catalog_payload(),
        "cases": [case.model_dump(mode="json") for case in cases],
    }

    response = ollama_chat(
        base_url=str(cfg.ollama.base_url),
        model=cfg.ollama.model,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(judge_input, ensure_ascii=False)},
        ],
        response_format="json",
        timeout_sec=cfg.agent.request_timeout_sec,
    )

    decision = EvalJudgeBatchDecision.model_validate_json(
        response["message"]["content"]
    )

    input_ids = {case.case_id for case in cases}
    output_ids = {decision.case_id for decision in decision.decisions}

    missing = input_ids - output_ids
    extra = output_ids - input_ids
    if missing or extra:
        raise ValueError(
            f"Judge returned mismatched case_ids: missing={sorted(missing)}, extra={sorted(extra)}"
        )

    return decision