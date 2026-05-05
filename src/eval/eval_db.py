from __future__ import annotations

import sqlite3

from src.app.artifact_paths import EVAL_ARTIFACT_PATHS
from src.app.db import init_app_schema, open_app_db


def open_eval_db() -> sqlite3.Connection:
    """
    Open the isolated eval SQLite database.

    The eval DB reuses the app schema for threads/turns because eval runs
    execute through ChatService.run_turn(...), which expects those tables.
    """
    return open_app_db(EVAL_ARTIFACT_PATHS.db_path)


def init_eval_schema(conn: sqlite3.Connection) -> None:
    """
    Initialize app tables plus eval-specific tables.
    """
    init_app_schema(conn)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_cases (
            case_id TEXT PRIMARY KEY,
            target_user_text TEXT NOT NULL,
            prior_user_questions_json TEXT NOT NULL DEFAULT '[]',
            given_state_json TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_results (
            case_id TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK (status IN ('unjudged', 'pass', 'fail', 'error')),
            final_answer TEXT NOT NULL,
            progress_events_json TEXT NOT NULL,
            failure_json TEXT NOT NULL DEFAULT '{}',

            FOREIGN KEY (case_id) REFERENCES eval_cases(case_id) ON DELETE CASCADE
        )
        """
    )

    conn.commit()