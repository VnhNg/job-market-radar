from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import langsmith as ls


@contextmanager
def trace_graph_node(
    *,
    thread_id: str,
    node_name: str,
    inputs: dict[str, Any],
) -> Iterator[Any]:
    """
    Small LangSmith trace wrapper for one graph node execution.
    Node wrappers will decide explicitly what outputs to record.
    """
    with ls.tracing_context(enabled=True):
        with ls.trace(
            name=f"complete.{node_name}",
            run_type="chain",
            inputs=inputs,
            tags=["assistant:complete", f"node:{node_name}"],
            metadata={
                "thread_id": thread_id,
                "graph": "complete",
                "node": node_name,
            },
        ) as run_tree:
            yield run_tree


@contextmanager
def trace_graph_turn(
    *,
    thread_id: str,
    user_question: str,
) -> Iterator[Any]:
    with ls.tracing_context(enabled=True):
        with ls.trace(
            name="complete.turn",
            run_type="chain",
            inputs={
                "thread_id": thread_id,
                "user_question": user_question,
            },
            tags=["assistant:complete", "entry:cli"],
            metadata={
                "thread_id": thread_id,
                "graph": "complete",
                "entrypoint": "cli",
            },
        ) as run_tree:
            with ls.tracing_context(enabled=False):
                yield run_tree