from __future__ import annotations

import argparse
from pprint import pprint

from src.eval.eval_db import init_eval_schema, open_eval_db
from src.eval.repos.case_repo import EvalCaseRepo
from src.eval.repos.result_repo import EvalResultRepo


DETAIL_EVENT_NODES = {
    "start_turn",
    "select_turn_memory",
    "route_base_strategy",
    "build_filter_value_pools",
    "plan_step_calls",
    "finalize_step_calls",
    "execute_step_calls",
    "commit_step_results",
    "prepare_next_step",
    "finalize_answer",
}


def list_cases() -> int:
    conn = open_eval_db()
    init_eval_schema(conn)

    try:
        cases = EvalCaseRepo(conn).list_cases()

        if not cases:
            print("No eval cases found.")
            return 0

        for case in cases:
            print(
                f"{case.case_id}\t"
                f"prior_count={len(case.prior_user_questions)}\t"
                f"has_state={case.given_state is not None}\t"
                f"{case.target_user_text}"
            )

        return 0
    finally:
        conn.close()


def list_results() -> int:
    conn = open_eval_db()
    init_eval_schema(conn)

    try:
        results = EvalResultRepo(conn).list_results()

        if not results:
            print("No eval results found.")
            return 0

        for result in results:
            first_failed_node = result.failure.get("first_failed_node") or "-"
            reason = result.failure.get("reason") or "-"

            print(
                f"{result.case_id}\t"
                f"{result.status}\t"
                f"first_failed_node={first_failed_node}\t"
                f"{reason}"
            )

        return 0
    finally:
        conn.close()


def show_result(case_id: str) -> int:
    conn = open_eval_db()
    init_eval_schema(conn)

    try:
        case = EvalCaseRepo(conn).get_case(case_id)
        result = EvalResultRepo(conn).get_result(case_id)

        if case is None:
            print(f"Eval case not found: {case_id}")
            return 1

        if result is None:
            print(f"Eval result not found: {case_id}")
            return 1

        print("CASE ID:")
        print(case.case_id)

        print("\nTARGET USER TEXT:")
        print(case.target_user_text)

        print("\nPRIOR USER QUESTIONS:")
        pprint(case.prior_user_questions, width=120)

        print("\nHAS GIVEN STATE:")
        print(case.given_state is not None)

        print("\nSTATUS:")
        print(result.status)

        print("\nFAILURE JSON:")
        pprint(result.failure, width=140)

        print("\nFINAL ANSWER:")
        print(result.final_answer)

        print("\nSELECTED PROGRESS EVENTS:")
        for event in result.progress_events:
            if event.get("node") not in DETAIL_EVENT_NODES:
                continue

            print("\n" + "=" * 80)
            print(event.get("node"))
            print("=" * 80)
            pprint(event, width=140)

        return 0
    finally:
        conn.close()


def delete_case(case_id: str) -> int:
    conn = open_eval_db()
    init_eval_schema(conn)

    try:
        cases = EvalCaseRepo(conn)
        existing = cases.get_case(case_id)

        if existing is None:
            print(f"Eval case not found: {case_id}")
            return 1

        cases.delete_case(case_id)
        print(f"Deleted eval case: {case_id}")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage local eval cases and results.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("cases", help="List eval cases")
    subparsers.add_parser("results", help="List latest eval results")

    result_parser = subparsers.add_parser("result", help="Show one eval case/result in detail")
    result_parser.add_argument("case_id")

    delete_parser = subparsers.add_parser("delete-case", help="Delete one eval case")
    delete_parser.add_argument("case_id")

    args = parser.parse_args()

    if args.command == "cases":
        return list_cases()

    if args.command == "results":
        return list_results()

    if args.command == "result":
        return show_result(args.case_id)

    if args.command == "delete-case":
        return delete_case(args.case_id)

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())