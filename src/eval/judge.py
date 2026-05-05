# src/eval/judge.py
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.assistant.core.ollama_client import ollama_chat
from src.assistant.core.registry import load_assistant_config


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
- If failed, identify the first graph node whose own responsibility was not satisfied.
- Evaluate the graph as a dependency pipeline, not as isolated outputs.

Graph dependency model:
Each node consumes state created by earlier nodes and writes state used by later nodes.
When an upstream node writes wrong, incomplete, or misleading state, downstream nodes may look wrong even if they only followed that upstream state.
Report the first node in graph order whose own responsibility failed.

Node responsibilities and downstream effects:

start_turn:
- Role: Establish the turn-level interpretation of the user message. It should preserve the user’s intent and create a useful planning text for downstream routing and planning.
- Common failures: Misreads the request, drops important constraints, over-resolves or under-resolves a follow-up, changes the task meaning, or creates planning text that points to a different task.
- Workflow effect: Later nodes may route, plan, and answer the wrong task even if their local behavior looks reasonable.

select_turn_memory:
- Role: Select only the prior tool traces that are relevant for the current turn, especially for follow-up questions referring to previous results.
- Common failures: Selects no memory when the question depends on prior results, selects irrelevant/stale memory, or misses the trace needed to resolve references such as “that company,” “the top region,” or “these results.”
- Workflow effect: Routing and planning may lack necessary grounded context or may be polluted by unrelated context.

route_base_strategy:
- Role: Choose the semantic base and strategy sequence that can produce the evidence shape required by the user request.
- Common failures: Chooses the wrong base, chooses a strategy whose tool sequence cannot produce the needed evidence shape, uses a single-step strategy for a task that needs candidate discovery plus downstream analysis, or uses a multi-step strategy when the request is directly answerable.
- Workflow effect: Later nodes are constrained to the chosen evidence path. A planning step may be locally valid for the selected tool but still unable to answer the user because the strategy itself is unsuitable.

Base concepts:
- jobs = posting-level base.
  Each row represents one observed job posting/listing.
  Use this base when the user asks about posting volume, posting distribution, concrete postings, titles, companies, locations, URLs, descriptions, or ordinary by number of postings.
  Typical evidence: job_count by channel/bundesland/company, or detail/sample rows from actual postings.

- replication = role-replication group base.
  Each row represents one grouped role identity, defined by channel + company + role_signature.
  A row summarizes multiple postings that appear to be the same role repeated or reposted across locations.
  Use this base when the user asks about reposting behavior, repeated roles, replicated postings, role_signature groups, distinct locations, repost ratio, or same roles appear across many locations.
  Typical evidence: postings, distinct_locations, repost_ratio, sample_title, sample_location, and role/group-level examples.
  
Tool evidence concepts used by strategies:
- B = analytics_breakdown.
  Produces aggregate/grouped evidence such as counts, rankings, distributions, grouped metrics, and comparisons by dimensions.
  It is not a row/detail evidence source.
- D = analytics_detail.
  Produces row/detail evidence such as concrete records, specific postings, specific groups, entities, and selected fields/columns from matching rows.
- S = analytics_sample.
  Produces example/sample-row evidence, especially useful when concrete target entities are not yet known and need to be grounded from real examples.

Strategy concepts:
- SINGLE_BREAKDOWN = B.
  One aggregate/grouped evidence step.
- SINGLE_DETAIL = D.
  One row/detail evidence step.
- SINGLE_SAMPLE = S.
  One example/sample evidence step.
- B_B = B -> B.
  Aggregate first, then a second aggregate using evidence from the first aggregate or memory.
- B_D = B -> D.
  Aggregate first to identify or constrain a candidate, then fetch row/detail evidence for that candidate.
- S_B = S -> B.
  Sample/example rows first to ground a candidate, then aggregate using that candidate.
- S_D = S -> D.
  Sample/example rows first to ground a candidate, then fetch row/detail evidence for that candidate.
- D_D = D -> D.
  Detail rows first to expose a concrete entity or slice, then a second detail query using that grounded entity or slice.
- B_B_B = B -> B -> B.
  Aggregate context, aggregate refinement, then final aggregate view.
- B_B_D = B -> B -> D.
  Aggregate context, aggregate refinement, then row/detail evidence for the grounded candidate or slice.
- S_B_D = S -> B -> D.
  Sample/example rows to ground a candidate, aggregate to refine that candidate or slice, then row/detail evidence.
- S_B_B = S -> B -> B.
  Sample/example rows to ground a candidate, aggregate using that candidate, then a second aggregate refinement.
- D_B_B = D -> B -> B.
  Detail rows to expose a concrete entity or slice, aggregate using it, then a second aggregate refinement.
- D_B_D = D -> B -> D.
  Detail rows to expose a concrete entity or slice, aggregate to refine it, then row/detail evidence for the refined candidate or slice.

route_base_strategy judgment guidance:
- Decide whether the selected strategy is capable in principle of producing the required evidence shape.
- Do not blame route_base_strategy merely because later nodes failed to use the selected strategy well.
- If the strategy is capable in principle but later candidate grounding, filtering, or parameter selection fails, blame the later node that failed.

init_execution:
- Role: Set up the execution structure for the selected strategy and current step.
- Common failures: Initializes the wrong number of calls, creates call state inconsistent with the strategy, or fails to reset per-step execution state.
- Workflow effect: Pool building, planning, and execution operate on the wrong call structure.

build_filter_value_pools:
- Role: Provide grounded candidate values for filters that planning may need. This is especially important when user language must be mapped to valid values or when upstream results should provide candidates for a later step.
- Common failures: Omits needed candidate pools, returns empty pools when upstream evidence contains usable candidates and actually has some rows, includes irrelevant candidates, or fails to ground user-mentioned entities.
- Workflow effect: Planning may be unable to choose the right filters or may ignore candidates discovered earlier.

plan_step_calls:
- Role: Choose concrete tool parameters for the current strategy step using the question, selected route, memory, filter pools, and prior step evidence.
- Common failures: Uses wrong metric, dimensions, filters, select columns, limits, or number of calls; fails to use grounded candidates from memory or upstream results; asks the right tool the wrong question.
- Workflow effect: Validation may accept the parameters and execution may succeed, but the returned evidence is irrelevant or insufficient.

finalize_step_calls:
- Role: Validate and repair planned tool parameters so execution receives legal and intent-preserving calls.
- Common failures: Allows invalid parameters through, repairs parameters in a way that changes intent, drops required filters/select columns, or fails to repair a recoverable planning mistake.
- Workflow effect: Execution runs a call that is technically invalid, semantically altered, or incomplete.

execute_step_calls:
- Role: Execute finalized tool calls and return usable tool evidence.
- Common failures: Tool execution fails, sends parameters different from the finalized intent, reuses irrelevant cached results, returns malformed payloads, or returns empty/unusable results when the query should have been avoidable or better grounded.
- Workflow effect: Commit and final answer have no reliable evidence to work with.

commit_step_results:
- Role: Turn tool results into reusable evidence units with enough meaning for later steps and final answer generation.
- Common failures: Does not commit useful results, summarizes results incorrectly, loses important entities/rankings, creates vague meanings, or commits misleading params/base/tool context.
- Workflow effect: Later steps and final answer may be grounded in incomplete or misleading trace memory.

prepare_next_step:
- Role: Move correctly from one strategy step to the next while preserving the evidence needed downstream.
- Common failures: Advances to the wrong step, resets needed context, creates wrong call state for the next step, or fails to continue a multi-step strategy.
- Workflow effect: Later steps no longer correspond to the intended strategy chain.

finalize_answer:
- Role: Produce the final user-facing answer using the committed evidence from the turn.
- Common failures: Hallucinates beyond the evidence, ignores important committed results, answers a different question, overstates empty/weak evidence, omits required caveats, or gives a vague answer when the evidence supports a concrete one.
- Workflow effect: Final consumer. Blame finalize_answer only when the judge-visible evidence clearly proves the answer misused, ignored, or contradicted sufficient evidence. Do not fail it for concise summaries or omissions.

Evaluation procedure:
1. Determine the evidence shape required by the user request.
2. Read progress events in graph order.
3. For each node, judge whether that node fulfilled its role given the upstream state available to it.
4. Do not blame a downstream node merely because it inherited bad upstream state.
5. Do not blame route_base_strategy when the selected strategy was capable in principle and a later node failed to use it correctly.
6. Do not require perfection. Mark fail only when the issue materially affects answering the user.
7. Use only the trace and final answer. Do not invent database facts.

Return raw JSON only:
{
  "decisions": [
    {
      "case_id": "same short input case_id",
      "status": "pass|fail|error",
      "first_failed_node": null,
      "reason": "short reason",
      "details": {}
    }
  ]
}

Rules:
- One decision per input case.
- Use the same short case_id from the input case.
- If status is pass, first_failed_node must be null.
- If status is fail/error, first_failed_node must be a graph node name or "run_turn" or "llm_judge".
- Do not wrap JSON in Markdown.
"""


def judge_runs_batch(*, cases: list[EvalJudgeCase]) -> EvalJudgeBatchDecision:
    if not cases:
        return EvalJudgeBatchDecision(decisions=[])

    cfg = load_assistant_config()

    local_to_original_case_id = {
        f"c{i + 1}": case.case_id
        for i, case in enumerate(cases)
    }

    judge_cases: list[dict[str, Any]] = []
    for i, case in enumerate(cases):
        payload = case.model_dump(mode="json")
        payload["case_id"] = f"c{i + 1}"
        judge_cases.append(payload)

    response = ollama_chat(
        base_url=str(cfg.ollama.base_url),
        model=cfg.ollama.model,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps({"cases": judge_cases}, ensure_ascii=False),
            },
        ],
        response_format="json",
        timeout_sec=cfg.agent.request_timeout_sec,
    )

    local_decision = EvalJudgeBatchDecision.model_validate_json(
        response["message"]["content"]
    )

    input_local_ids = set(local_to_original_case_id)
    output_local_ids = {decision.case_id for decision in local_decision.decisions}

    missing = input_local_ids - output_local_ids
    extra = output_local_ids - input_local_ids
    if missing or extra:
        raise ValueError(
            f"Judge returned mismatched local case_ids: "
            f"missing={sorted(missing)}, extra={sorted(extra)}"
        )

    return EvalJudgeBatchDecision(
        decisions=[
            EvalJudgeDecision(
                case_id=local_to_original_case_id[decision.case_id],
                status=decision.status,
                first_failed_node=decision.first_failed_node,
                reason=decision.reason,
                details=decision.details,
            )
            for decision in local_decision.decisions
        ]
    )