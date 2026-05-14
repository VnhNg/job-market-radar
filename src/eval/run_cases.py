from __future__ import annotations

import argparse
import traceback
from dataclasses import dataclass
from typing import Any

from src.app.services.chat_service import ChatService
from src.assistant.modes.complete.graph.infra.checkpoints import thread_config
from src.assistant.modes.complete.state import GraphState
from src.eval.eval_db import init_eval_schema, open_eval_db
from src.eval.repos.case_repo import EvalCase, EvalCaseRepo
from src.eval.repos.result_repo import EvalResultRepo


FAILED_REPLAY_STATUSES = {"fail", "error"}


@dataclass(frozen=True)
class CompletedCaseRun:
    case: EvalCase
    eval_thread_id: str


def reset_eval_execution_artifacts(service: ChatService) -> None:
    """
    Delete temporary eval execution artifacts from the previous eval run.

    Durable eval artifacts:
    - eval_cases
    - eval_results

    Temporary execution artifacts:
    - eval threads
    - eval turns
    - eval checkpoints
    - eval LangSmith traces, if configured
    """
    thread_ids = [row.id for row in service.list_threads()]

    for thread_id in thread_ids:
        service.delete_thread(thread_id)


def select_cases_to_run(
    *,
    case_repo: EvalCaseRepo,
    result_repo: EvalResultRepo,
    failed_only: bool,
    new_only: bool,
) -> list[EvalCase]:
    if failed_only and new_only:
        raise ValueError("failed_only and new_only cannot both be true")

    cases = case_repo.list_cases()
    results_by_case_id = {
        result.case_id: result
        for result in result_repo.list_results()
    }

    if failed_only:
        return [
            case
            for case in cases
            if (
                case.case_id in results_by_case_id
                and results_by_case_id[case.case_id].status in FAILED_REPLAY_STATUSES
            )
        ]

    if new_only:
        return [
            case
            for case in cases
            if case.case_id not in results_by_case_id
        ]

    return cases


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
            max_prior_user_questions=0,
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


def _last_completed_node(progress_events: list[dict[str, object]]) -> object:
    if not progress_events:
        return None
    return progress_events[-1].get("node")


def _error_failure(
    error: BaseException,
    *,
    eval_thread_id: str | None,
    progress_events: list[dict[str, object]],
) -> dict[str, Any]:
    return {
        "first_failed_node": "run_turn",
        "reason": "Eval case replay raised an exception.",
        "details": {
            "eval_thread_id": eval_thread_id,
            "last_completed_node": _last_completed_node(progress_events),
            "progress_event_count": len(progress_events),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
        },
    }


def run_case(
    *,
    service: ChatService,
    case: EvalCase,
    result_repo: EvalResultRepo,
) -> CompletedCaseRun:
    thread = service.create_thread()
    captured_events: list[dict[str, object]] = []

    def on_progress_event(event: dict[str, object]) -> None:
        captured_events.append(event)

    try:
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
            on_progress_event=on_progress_event,
        )

        result_repo.save_result(
            case_id=case.case_id,
            status="unjudged",
            final_answer=ctx.final_answer or "",
            progress_events=ctx.progress_events,
            failure={},
        )

        return CompletedCaseRun(
            case=case,
            eval_thread_id=thread.id,
        )

    except Exception as error:
        result_repo.save_result(
            case_id=case.case_id,
            status="error",
            final_answer="",
            progress_events=captured_events,
            failure=_error_failure(
                error,
                eval_thread_id=thread.id,
                progress_events=captured_events,
            ),
        )
        raise


def run_cases(*, failed_only: bool, new_only: bool) -> int:
    conn = open_eval_db()
    init_eval_schema(conn)

    case_repo = EvalCaseRepo(conn)
    result_repo = EvalResultRepo(conn)

    try:
        cases = select_cases_to_run(
            case_repo=case_repo,
            result_repo=result_repo,
            failed_only=failed_only,
            new_only=new_only,
        )
    except ValueError as error:
        conn.close()
        raise SystemExit(str(error))

    if not cases:
        if failed_only:
            print("No failed/error eval cases found.")
        elif new_only:
            print("No new eval cases found.")
        else:
            print("No eval cases found.")
        conn.close()
        return 0

    service = ChatService.open_eval()

    try:
        reset_eval_execution_artifacts(service)

        if failed_only:
            print(f"Replaying failed/error cases only: {len(cases)}")
        elif new_only:
            print(f"Replaying new cases only: {len(cases)}")
        else:
            print(f"Replaying all eval cases: {len(cases)}")

        for case in cases:
            try:
                run_case(
                    service=service,
                    case=case,
                    result_repo=result_repo,
                )
                print(f"{case.case_id}: unjudged")

            except Exception as error:
                saved = result_repo.get_result(case.case_id)
                details = (saved.failure if saved else {}).get("details", {})
                last_completed_node = details.get("last_completed_node") or "-"
                event_count = details.get("progress_event_count", 0)

                print(
                    f"{case.case_id}: error during replay "
                    f"({type(error).__name__}: {error}; "
                    f"last_completed_node={last_completed_node}; "
                    f"progress_events={event_count})"
                )

    finally:
        service.close()
        conn.close()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay eval cases through the app ChatService.")

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--failed-only",
        action="store_true",
        help="Replay only cases whose latest result status is fail or error.",
    )
    group.add_argument(
        "--new-only",
        action="store_true",
        help="Replay only cases that do not yet have an eval result.",
    )

    args = parser.parse_args()

    return run_cases(
        failed_only=args.failed_only,
        new_only=args.new_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())