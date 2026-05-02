from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    target_user_text: str
    prior_user_questions: list[str]
    given_state: dict[str, Any] | None


class EvalCaseRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_case(
        self,
        *,
        case_id: str,
        target_user_text: str,
        prior_user_questions: list[str] | None = None,
        given_state: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO eval_cases (
                case_id,
                target_user_text,
                prior_user_questions_json,
                given_state_json
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                case_id,
                target_user_text,
                json.dumps(prior_user_questions or [], ensure_ascii=False),
                json.dumps(given_state, ensure_ascii=False) if given_state is not None else None,
            ),
        )
        self.conn.commit()

    def get_case(self, case_id: str) -> EvalCase | None:
        row = self.conn.execute(
            """
            SELECT
                case_id,
                target_user_text,
                prior_user_questions_json,
                given_state_json
            FROM eval_cases
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()

        if row is None:
            return None

        return self._row_to_case(row)

    def list_cases(self) -> list[EvalCase]:
        rows = self.conn.execute(
            """
            SELECT
                case_id,
                target_user_text,
                prior_user_questions_json,
                given_state_json
            FROM eval_cases
            ORDER BY case_id
            """
        ).fetchall()

        return [self._row_to_case(row) for row in rows]

    def _row_to_case(self, row: sqlite3.Row) -> EvalCase:
        return EvalCase(
            case_id=row["case_id"],
            target_user_text=row["target_user_text"],
            prior_user_questions=json.loads(row["prior_user_questions_json"]),
            given_state=json.loads(row["given_state_json"]) if row["given_state_json"] else None,
        )
    
    def exists_case(self, case_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1
            FROM eval_cases
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()

        return row is not None
       
    def delete_case(self, case_id: str) -> None:
        self.conn.execute(
            """
            DELETE FROM eval_cases
            WHERE case_id = ?
            """,
            (case_id,),
        )
        self.conn.commit()