# src/eval/run_eval.py
from __future__ import annotations

import argparse
import traceback
from collections import Counter

from src.eval.eval_db import init_eval_schema, open_eval_db
from src.eval.judge import EvalJudgeCase, judge_runs_batch
from src.eval.repos.case_repo import EvalCaseRepo
from src.eval.repos.result_repo import EvalResult, EvalResultRepo


JUDGEABLE_STATUSES = {"unjudged", "pass", "fail"}


def _batches(items: list[EvalResult], batch_size: int) -> list[list[EvalResult]]:
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def _is_failed_llm_judge_result(result: EvalResult) -> bool:
    return (
        result.status == "error"
        and result.failure.get("first_failed_node") == "llm_judge"
    )


def _is_judgeable_result(result: EvalResult) -> bool:
    if result.status in JUDGEABLE_STATUSES:
        return True
    return _is_failed_llm_judge_result(result)


def select_results_to_judge(
    *,
    result_repo: EvalResultRepo,
    unjudged_only: bool,
    failed_llm_judge_only: bool,
) -> list[EvalResult]:
    results = result_repo.list_results()

    if not unjudged_only and not failed_llm_judge_only:
        return [
            result
            for result in results
            if _is_judgeable_result(result)
        ]

    selected: list[EvalResult] = []

    for result in results:
        if unjudged_only and result.status == "unjudged":
            selected.append(result)
            continue

        if failed_llm_judge_only and _is_failed_llm_judge_result(result):
            selected.append(result)
            continue

    return selected


def _selection_label(*, unjudged_only: bool, failed_llm_judge_only: bool) -> str:
    if unjudged_only and failed_llm_judge_only:
        return "unjudged + failed LLM judge"
    if unjudged_only:
        return "unjudged only"
    if failed_llm_judge_only:
        return "failed LLM judge only"
    return "all judgeable results"


def _judge_error_failure(error: BaseException) -> dict[str, object]:
    return {
        "first_failed_node": "llm_judge",
        "reason": "LLM judge failed to return a valid decision.",
        "details": {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
        },
    }


def print_summary(result_repo: EvalResultRepo) -> None:
    results = result_repo.list_results()

    status_counts = Counter(result.status for result in results)
    failed_nodes = Counter(
        result.failure.get("first_failed_node")
        for result in results
        if result.failure.get("first_failed_node")
    )

    print()
    print("Eval summary")
    print(f"Total:    {len(results)}")
    print(f"Unjudged: {status_counts.get('unjudged', 0)}")
    print(f"Pass:     {status_counts.get('pass', 0)}")
    print(f"Fail:     {status_counts.get('fail', 0)}")
    print(f"Error:    {status_counts.get('error', 0)}")

    if failed_nodes:
        print()
        print("First failed nodes:")
        for node, count in failed_nodes.most_common():
            print(f"{node}: {count}")


def run_eval(
    *,
    judge_batch_size: int,
    unjudged_only: bool,
    failed_llm_judge_only: bool,
) -> int:
    conn = open_eval_db()
    init_eval_schema(conn)

    case_repo = EvalCaseRepo(conn)
    result_repo = EvalResultRepo(conn)

    selected_results = select_results_to_judge(
        result_repo=result_repo,
        unjudged_only=unjudged_only,
        failed_llm_judge_only=failed_llm_judge_only,
    )

    if not selected_results:
        print(
            "No eval results selected for judging "
            f"({ _selection_label(unjudged_only=unjudged_only, failed_llm_judge_only=failed_llm_judge_only) })."
        )
        print_summary(result_repo)
        conn.close()
        return 0

    print(f"Judging results: {len(selected_results)}")
    print(
        "Selection: "
        f"{_selection_label(unjudged_only=unjudged_only, failed_llm_judge_only=failed_llm_judge_only)}"
    )

    try:
        for batch in _batches(selected_results, judge_batch_size):
            try:
                judge_cases: list[EvalJudgeCase] = []

                for result in batch:
                    case = case_repo.get_case(result.case_id)
                    if case is None:
                        raise RuntimeError(
                            f"Eval case not found for result: {result.case_id}"
                        )

                    judge_cases.append(
                        EvalJudgeCase(
                            case_id=result.case_id,
                            target_user_text=case.target_user_text,
                            prior_user_questions=case.prior_user_questions,
                            progress_events=result.progress_events,
                            final_answer=result.final_answer,
                        )
                    )

                judge_decision = judge_runs_batch(cases=judge_cases)
                decisions_by_case_id = {
                    decision.case_id: decision
                    for decision in judge_decision.decisions
                }

                for result in batch:
                    decision = decisions_by_case_id[result.case_id]

                    result_repo.save_result(
                        case_id=result.case_id,
                        status=decision.status,
                        final_answer=result.final_answer,
                        progress_events=result.progress_events,
                        failure=decision.to_failure_json(),
                    )

                    print(f"{result.case_id}: {decision.status}")

            except Exception as error:
                for result in batch:
                    result_repo.save_result(
                        case_id=result.case_id,
                        status="error",
                        final_answer=result.final_answer,
                        progress_events=result.progress_events,
                        failure=_judge_error_failure(error),
                    )

                    print(
                        f"{result.case_id}: error during judging "
                        f"({type(error).__name__}: {error})"
                    )

        print_summary(result_repo)

    finally:
        conn.close()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the LLM judge over saved eval case results."
    )
    parser.add_argument("--judge-batch-size", type=int, default=3)
    parser.add_argument(
        "--unjudged-only",
        action="store_true",
        help="Judge only results with status='unjudged'.",
    )
    parser.add_argument(
        "--failed-llm-judge-only",
        action="store_true",
        help="Judge only results whose previous error came from the LLM judge.",
    )

    args = parser.parse_args()

    if args.judge_batch_size < 1:
        raise SystemExit("--judge-batch-size must be >= 1")

    return run_eval(
        judge_batch_size=args.judge_batch_size,
        unjudged_only=args.unjudged_only,
        failed_llm_judge_only=args.failed_llm_judge_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())