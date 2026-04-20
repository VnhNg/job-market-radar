from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ThreadRow:
    id: str
    thread_number: int
    title: str
    created_at: str
    updated_at: str


class ThreadRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list_threads(self) -> list[ThreadRow]:
        rows = self.conn.execute(
            """
            SELECT id, thread_number, title, created_at, updated_at
            FROM threads
            ORDER BY thread_number DESC
            """
        ).fetchall()

        return [
            ThreadRow(
                id=row["id"],
                thread_number=row["thread_number"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def get_thread(self, thread_id: str) -> ThreadRow | None:
        row = self.conn.execute(
            """
            SELECT id, thread_number, title, created_at, updated_at
            FROM threads
            WHERE id = ?
            """,
            (thread_id,),
        ).fetchone()

        if row is None:
            return None

        return ThreadRow(
            id=row["id"],
            thread_number=row["thread_number"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_thread(self, *, title: str) -> ThreadRow:
        now = utc_now_iso()
        thread_id = str(uuid.uuid4())

        row = self.conn.execute(
            """
            SELECT COALESCE(MAX(thread_number), 0) + 1 AS next_number
            FROM threads
            """
        ).fetchone()
        thread_number = int(row["next_number"])

        self.conn.execute(
            """
            INSERT INTO threads (id, thread_number, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (thread_id, thread_number, title, now, now),
        )
        self.conn.commit()

        return ThreadRow(
            id=thread_id,
            thread_number=thread_number,
            title=title,
            created_at=now,
            updated_at=now,
        )

    def update_title(self, *, thread_id: str, title: str) -> None:
        now = utc_now_iso()
        self.conn.execute(
            """
            UPDATE threads
            SET title = ?, updated_at = ?
            WHERE id = ?
            """,
            (title, now, thread_id),
        )
        self.conn.commit()

    
    def delete_thread(self, thread_id: str) -> None:
        self.conn.execute(
            """
            DELETE FROM threads
            WHERE id = ?
            """,
            (thread_id,),
        )
        self.conn.commit()