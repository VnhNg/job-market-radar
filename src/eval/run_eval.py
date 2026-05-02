# src/eval/run_eval.py
from __future__ import annotations

import argparse
import traceback
from dataclasses import dataclass
from typing import Any

from src.app.services.chat_service import ChatService
from src.assistant.modes.complete.graph.infra.checkpoints import thread_config
from src.assistant.modes.complete.state import GraphState
from src.eval.eval_db import init_eval_schema, open_eval_db
from src.eval.judge import EvalJudgeCase, judge_runs_batch
from src.eval.repos.case_repo import EvalCase, EvalCaseRepo
from src.eval.repos.result_repo import EvalResultRepo


@dataclass(frozen=True)
class CompletedEvalRun:
    case: EvalCase
    judge_case: EvalJudgeCase
    eval_thread_id: str


def _seed_prior_user_questions(
    service: ChatService,
    *,
    thread_id: str,
    prior_user_questions: list[str],
) -> None:
    for question in prior_user_questions:
        service.turn_repo.create_turn(
            thread_id=thread_id,
            user_text=question,
            assistant_text="[eval seed: prior user question only]",
            checkpoint_id="[eval seed: no checkpoint]",
        )


def _seed_given_state(
    service: ChatService,
    *,
    thread_id: str,
    given_state: dict[str, Any] | None,
) -> None:
    if given_state is None:
        return

    state = GraphState.model_validate(given_state)
    service.bootstrap.graph.update_state(thread_config(thread_id), state)


def _error_failure(error: BaseException, *, eval_thread_id: str | None = None) -> dict[str, Any]:
    return {
        "first_failed_node": "run_turn",
        "reason": "Eval execution raised an exception.",
        "details": {
            "eval_thread_id": eval_thread_id,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
        },
    }


def _judge_error_failure(error: BaseException) -> dict[str, Any]:
    return {
        "first_failed_node": "llm_judge",
        "reason": "LLM judge failed to return a valid decision.",
        "details": {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
        },
    }


def reset_eval_execution_artifacts(service: ChatService) -> None:
    """
    Delete temporary eval execution artifacts from previous eval runs.

    Durable eval artifacts are eval_cases and eval_results.
    Temporary execution artifacts are threads, turns, checkpoints, and eval LangSmith traces.
    """
    thread_ids = [
        row.id
        for row in service.list_threads()
    ]

    for thread_id in thread_ids:
        service.delete_thread(thread_id)


def run_case_without_judging(
    *,
    service: ChatService,
    case: EvalCase,
) -> CompletedEvalRun:
    thread = service.create_thread()

    _seed_prior_user_questions(
        service,
        thread_id=thread.id,
        prior_user_questions=case.prior_user_questions,
    )
    _seed_given_state(
        service,
        thread_id=thread.id,
        given_state=case.given_state,
    )

    _, ctx = service.run_turn(
        thread_id=thread.id,
        user_text=case.target_user_text,
        max_prior_user_questions=len(case.prior_user_questions),
    )

    return CompletedEvalRun(
        case=case,
        eval_thread_id=thread.id,
        judge_case=EvalJudgeCase(
            case_id=case.case_id,
            target_user_text=case.target_user_text,
            prior_user_questions=case.prior_user_questions,
            progress_events=ctx.progress_events,
            final_answer=ctx.final_answer or "",
        ),
    )


def _batches(items: list[CompletedEvalRun], batch_size: int) -> list[list[CompletedEvalRun]]:
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def run_eval(
    *,
    judge_batch_size: int,
) -> int:
    conn = open_eval_db()
    init_eval_schema(conn)

    case_repo = EvalCaseRepo(conn)
    result_repo = EvalResultRepo(conn)

    cases = case_repo.list_cases()
    if not cases:
        print("No eval cases found.")
        conn.close()
        return 0

    service = ChatService.open_eval()
    completed: list[CompletedEvalRun] = []
    reset_eval_execution_artifacts(service)

    try:
        for case in cases:
            try:
                completed_run = run_case_without_judging(
                    service=service,
                    case=case,
                )
                completed.append(completed_run)
                print(f"{case.case_id}: ran")
            except Exception as error:
                result_repo.save_result(
                    case_id=case.case_id,
                    status="error",
                    final_answer="",
                    progress_events=[],
                    failure=_error_failure(error),
                )
                print(f"{case.case_id}: error during run ({type(error).__name__}: {error})")

        for batch in _batches(completed, judge_batch_size):
            try:
                judge_decision = judge_runs_batch(
                    cases=[item.judge_case for item in batch],
                )
                decisions_by_case_id = {
                    decision.case_id: decision
                    for decision in judge_decision.decisions
                }

                for item in batch:
                    decision = decisions_by_case_id[item.case.case_id]

                    result_repo.save_result(
                        case_id=item.case.case_id,
                        status=decision.status,
                        final_answer=item.judge_case.final_answer,
                        progress_events=item.judge_case.progress_events,
                        failure=decision.to_failure_json(),
                    )

                    print(f"{item.case.case_id}: {decision.status}")

            except Exception as error:
                for item in batch:
                    result_repo.save_result(
                        case_id=item.case.case_id,
                        status="error",
                        final_answer=item.judge_case.final_answer,
                        progress_events=item.judge_case.progress_events,
                        failure=_judge_error_failure(error),
                    )
                    print(
                        f"{item.case.case_id}: error during judging "
                        f"({type(error).__name__}: {error})"
                    )

    finally:
        service.close()
        conn.close()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run eval cases through the app ChatService.")
    parser.add_argument("--judge-batch-size", type=int, default=3)
    args = parser.parse_args()

    if args.judge_batch_size < 1:
        raise SystemExit("--judge-batch-size must be >= 1")

    return run_eval(judge_batch_size=args.judge_batch_size)


if __name__ == "__main__":
    raise SystemExit(main())