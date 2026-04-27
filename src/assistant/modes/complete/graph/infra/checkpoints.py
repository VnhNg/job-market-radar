from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any, Literal

from langgraph.checkpoint.memory import InMemorySaver

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError:  # pragma: no cover
    SqliteSaver = None  # type: ignore[assignment]


CheckpointKind = Literal["memory", "sqlite"]


@dataclass
class CheckpointRuntime:
    checkpointer: Any
    kind: CheckpointKind
    path: Path | None = None
    _conn: sqlite3.Connection | None = None

    def delete_thread(self, thread_id: str) -> None:
            if not thread_id.strip():
                raise ValueError("thread_id must be non-empty")
            self.checkpointer.delete_thread(thread_id)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def make_checkpointer(
    *,
    kind: CheckpointKind = "sqlite",
    path: str | Path = ".local/app/langgraph/complete/checkpoints.sqlite",
) -> CheckpointRuntime:
    """
    Build a LangGraph checkpointer for Complete Mode.

    - memory: ephemeral, good for quick experiments
    - sqlite: local persisted thread state across process restarts
    """
    if kind == "memory":
        return CheckpointRuntime(
            checkpointer=InMemorySaver(),
            kind="memory",
        )

    if SqliteSaver is None:
        raise RuntimeError(
            "SqliteSaver is unavailable. Install langgraph-checkpoint-sqlite "
            "or switch to kind='memory'."
        )

    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    return CheckpointRuntime(
        checkpointer=checkpointer,
        kind="sqlite",
        path=db_path,
        _conn=conn,
    )


def thread_config(thread_id: str) -> dict[str, dict[str, str]]:
    """
    LangGraph thread-scoped config.
    """
    if not thread_id.strip():
        raise ValueError("thread_id must be non-empty")
    return {"configurable": {"thread_id": thread_id}}


def checkpoint_config(thread_id: str, checkpoint_id: str) -> dict[str, dict[str, str]]:
    """
    Address one exact checkpoint.
    """
    if not thread_id.strip():
        raise ValueError("thread_id must be non-empty")
    if not checkpoint_id.strip():
        raise ValueError("checkpoint_id must be non-empty")
    return {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}


def has_checkpoint(graph, *, thread_id: str) -> bool:
    """
    Return True if the graph already has persisted state for this thread.
    """
    try:
        snapshot = graph.get_state(thread_config(thread_id))
    except Exception:
        return False

    values = getattr(snapshot, "values", None)
    return bool(values)


def latest_checkpoint_id(graph, *, thread_id: str) -> str | None:
    """
    Return the latest checkpoint id currently stored for this thread.

    Intended to be called immediately after a successful graph invocation,
    where the latest checkpoint corresponds to the final checkpoint of that turn.
    """
    if not thread_id.strip():
        raise ValueError("thread_id must be non-empty")

    snapshot = graph.get_state(thread_config(thread_id))
    if snapshot is None:
        return None

    config = getattr(snapshot, "config", None) or {}
    configurable = config.get("configurable", {})
    checkpoint_id = configurable.get("checkpoint_id")
    return checkpoint_id