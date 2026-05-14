from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from src.app.services.chat_service import ChatService
from src.assistant.modes.complete.graph.infra.checkpoints import checkpoint_config
from src.assistant.modes.complete.state import GraphState
from src.eval.eval_db import init_eval_schema, open_eval_db
from src.eval.repos.case_repo import EvalCaseRepo


def _default_case_id(turn_id: str) -> str:
    return f"ui_{turn_id}"


@dataclass(frozen=True)
class EvalCaptureResult:
    case_id: str
    created: bool


@dataclass
class EvalCaptureService:
    """
    Captures a completed app turn as a minimal eval case.

    The eval case reproduces the situation before the target turn:
    - target_user_text: selected turn's user_text
    - prior_user_questions: same prior-question window size used when that turn ran
    - given_state: graph checkpoint state after the previous turn
    """

    app_service: ChatService
    eval_conn: sqlite3.Connection
    case_repo: EvalCaseRepo

    @classmethod
    def open_for_app_service(cls, app_service: ChatService) -> "EvalCaptureService":
        conn = open_eval_db()
        init_eval_schema(conn)

        return cls(
            app_service=app_service,
            eval_conn=conn,
            case_repo=EvalCaseRepo(conn),
        )

    def close(self) -> None:
        self.eval_conn.close()

    def capture_turn(self, *, turn_id: str, case_id: str | None = None) -> EvalCaptureResult:
        target_turn = self.app_service.turn_repo.get_turn(turn_id)
        if target_turn is None:
            raise ValueError(f"Turn not found: {turn_id}")

        final_case_id = case_id or _default_case_id(target_turn.id)

        if self.case_repo.exists_case(final_case_id):
            return EvalCaptureResult(case_id=final_case_id, created=False)

        turns = self.app_service.turn_repo.list_turns(thread_id=target_turn.thread_id)
        prior_turns = [
            turn
            for turn in turns
            if turn.position < target_turn.position
        ]

        prior_user_questions = self._prior_user_questions_for_target_turn(
            prior_turns=prior_turns,
            max_prior_user_questions=target_turn.max_prior_user_questions,
        )

        given_state = self._given_state_before_target_turn(
            target_thread_id=target_turn.thread_id,
            prior_turns=prior_turns,
        )

        self.case_repo.save_case(
            case_id=final_case_id,
            target_user_text=target_turn.user_text,
            prior_user_questions=prior_user_questions,
            given_state=given_state,
        )

        return EvalCaptureResult(case_id=final_case_id, created=True)

    def _prior_user_questions_for_target_turn(
        self,
        *,
        prior_turns,
        max_prior_user_questions: int,
    ) -> list[str]:
        if max_prior_user_questions < 1:
            return []

        return [
            turn.user_text
            for turn in prior_turns[-max_prior_user_questions:]
        ]

    def _given_state_before_target_turn(
        self,
        *,
        target_thread_id: str,
        prior_turns,
    ) -> dict[str, Any] | None:
        if not prior_turns:
            return None

        previous_turn = prior_turns[-1]

        snapshot = self.app_service.bootstrap.graph.get_state(
            checkpoint_config(target_thread_id, previous_turn.checkpoint_id)
        )

        values = getattr(snapshot, "values", None)
        if not values:
            raise RuntimeError(
                f"Previous checkpoint has no state values: turn_id={previous_turn.id}"
            )

        state = GraphState.model_validate(values)
        return state.model_dump(mode="json")