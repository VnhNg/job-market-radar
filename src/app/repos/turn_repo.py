from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TurnRow:
    id: str
    thread_id: str
    position: int
    user_text: str
    assistant_text: str
    checkpoint_id: str
    created_at: str
    updated_at: str


class TurnRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list_turns(self, *, thread_id: str) -> list[TurnRow]:
        rows = self.conn.execute(
            """
            SELECT id, thread_id, position, user_text, assistant_text, checkpoint_id, created_at, updated_at
            FROM turns
            WHERE thread_id = ?
            ORDER BY position ASC
            """,
            (thread_id,),
        ).fetchall()

        return [
            TurnRow(
                id=row["id"],
                thread_id=row["thread_id"],
                position=row["position"],
                user_text=row["user_text"],
                assistant_text=row["assistant_text"],
                checkpoint_id=row["checkpoint_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]
    
    def get_turn(self, turn_id: str) -> TurnRow | None:
        row = self.conn.execute(
            """
            SELECT id, thread_id, position, user_text, assistant_text, checkpoint_id, created_at, updated_at
            FROM turns
            WHERE id = ?
            """,
            (turn_id,),
        ).fetchone()

        if row is None:
            return None

        return TurnRow(
            id=row["id"],
            thread_id=row["thread_id"],
            position=row["position"],
            user_text=row["user_text"],
            assistant_text=row["assistant_text"],
            checkpoint_id=row["checkpoint_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_turn(
        self,
        *,
        thread_id: str,
        user_text: str,
        assistant_text: str,
        checkpoint_id: str,
    ) -> TurnRow:
        now = utc_now_iso()
        turn_id = str(uuid.uuid4())

        row = self.conn.execute(
            """
            SELECT COALESCE(MAX(position), 0) + 1 AS next_position
            FROM turns
            WHERE thread_id = ?
            """,
            (thread_id,),
        ).fetchone()
        position = int(row["next_position"])

        self.conn.execute(
            """
            INSERT INTO turns (
                id,
                thread_id,
                position,
                user_text,
                assistant_text,
                checkpoint_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn_id,
                thread_id,
                position,
                user_text,
                assistant_text,
                checkpoint_id,
                now,
                now,
            ),
        )
        self.conn.commit()

        return TurnRow(
            id=turn_id,
            thread_id=thread_id,
            position=position,
            user_text=user_text,
            assistant_text=assistant_text,
            checkpoint_id=checkpoint_id,
            created_at=now,
            updated_at=now,
        )