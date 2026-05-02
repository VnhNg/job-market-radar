from __future__ import annotations

import sqlite3
from pathlib import Path


DEFAULT_APP_DB_PATH = Path(".local/app/app.sqlite")


def open_app_db(path: str | Path = DEFAULT_APP_DB_PATH) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_app_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS threads (
            id TEXT PRIMARY KEY,
            thread_number INTEGER NOT NULL UNIQUE,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS turns (
            id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            user_text TEXT NOT NULL,
            max_prior_user_questions INTEGER,
            assistant_text TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE,
            UNIQUE (thread_id, position)
        )
        """
    )

    existing_turn_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(turns)").fetchall()
    }

    if "max_prior_user_questions" not in existing_turn_columns:
        conn.execute(
            """
            ALTER TABLE turns
            ADD COLUMN max_prior_user_questions INTEGER
            """
        )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_turns_thread_id_position
        ON turns(thread_id, position)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_turns_checkpoint_id
        ON turns(checkpoint_id)
        """
    )

    conn.commit()