from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Literal


EvalStatus = Literal["unjudged", "pass", "fail", "error"]


@dataclass(frozen=True)
class EvalResult:
    case_id: str
    status: EvalStatus
    final_answer: str
    progress_events: list[dict[str, Any]]
    failure: dict[str, Any]


class EvalResultRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_result(
        self,
        *,
        case_id: str,
        status: EvalStatus,
        final_answer: str,
        progress_events: list[dict[str, Any]],
        failure: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO eval_results (
                case_id,
                status,
                final_answer,
                progress_events_json,
                failure_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                case_id,
                status,
                final_answer,
                json.dumps(progress_events, ensure_ascii=False),
                json.dumps(failure or {}, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def get_result(self, case_id: str) -> EvalResult | None:
        row = self.conn.execute(
            """
            SELECT
                case_id,
                status,
                final_answer,
                progress_events_json,
                failure_json
            FROM eval_results
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()

        if row is None:
            return None

        return self._row_to_result(row)

    def list_results(self) -> list[EvalResult]:
        rows = self.conn.execute(
            """
            SELECT
                case_id,
                status,
                final_answer,
                progress_events_json,
                failure_json
            FROM eval_results
            ORDER BY case_id
            """
        ).fetchall()

        return [self._row_to_result(row) for row in rows]

    def _row_to_result(self, row: sqlite3.Row) -> EvalResult:
        return EvalResult(
            case_id=row["case_id"],
            status=row["status"],
            final_answer=row["final_answer"],
            progress_events=json.loads(row["progress_events_json"]),
            failure=json.loads(row["failure_json"]),
        )
    
    def delete_result(self, case_id: str) -> None:
        self.conn.execute(
            """
            DELETE FROM eval_results
            WHERE case_id = ?
            """,
            (case_id,),
        )
        self.conn.commit()