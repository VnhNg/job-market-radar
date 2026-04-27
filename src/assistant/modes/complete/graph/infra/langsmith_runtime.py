from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

import langsmith as ls
from langsmith import Client


@dataclass
class LangSmithRuntime:
    client: Client
    project_name: str | None = None

    @classmethod
    def open(cls, *, project_name: str | None) -> "LangSmithRuntime":
        return cls(
            client=Client(),
            project_name=project_name,
        )

    @contextmanager
    def trace_node(
        self,
        *,
        thread_id: str,
        node_name: str,
        inputs: dict[str, Any],
    ) -> Iterator[Any]:
        if not self.project_name:
            yield None
            return

        with ls.tracing_context(
            enabled=True,
            project_name=self.project_name,
            client=self.client,
        ):
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
                project_name=self.project_name,
                client=self.client,
            ) as run_tree:
                yield run_tree

    @contextmanager
    def trace_turn(
        self,
        *,
        thread_id: str,
        user_question: str,
    ) -> Iterator[Any]:
        if not self.project_name:
            yield None
            return

        with ls.tracing_context(
            enabled=True,
            project_name=self.project_name,
            client=self.client,
        ):
            with ls.trace(
                name="complete.turn",
                run_type="chain",
                inputs={
                    "thread_id": thread_id,
                    "user_question": user_question,
                },
                tags=["assistant:complete", "entry:ui"],
                metadata={
                    "thread_id": thread_id,
                    "graph": "complete",
                    "entrypoint": "ui",
                },
                project_name=self.project_name,
                client=self.client,
            ) as run_tree:
                with ls.tracing_context(enabled=False):
                    yield run_tree

    def delete_thread(self, thread_id: str) -> None:
        if not thread_id.strip():
            raise ValueError("thread_id must be non-empty")

        # If tracing is disabled for this artifact profile, deletion is a no-op.
        if not self.project_name:
            return
        if not self.client.api_key:
            return

        filter_string = (
            f"and(eq(metadata_key, 'thread_id'), eq(metadata_value, '{thread_id}'))"
        )

        runs = list(
            self.client.list_runs(
                project_name=self.project_name,
                filter=filter_string,
                is_root=True,
            )
        )

        if not runs:
            return

        session_ids = {
            str(getattr(run, "session_id", ""))
            for run in runs
            if getattr(run, "session_id", None)
        }
        if len(session_ids) != 1:
            raise RuntimeError(
                f"Expected exactly one LangSmith session_id for thread {thread_id}, got {session_ids}"
            )

        session_id = next(iter(session_ids))
        trace_ids = [str(run.id) for run in runs]

        url = f"{self.client.api_url.rstrip('/')}/api/v1/runs/delete"
        headers = {
            "x-api-key": self.client.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "session_id": session_id,
            "trace_ids": trace_ids,
        }

        response = self.client.session.post(
            url,
            headers=headers,
            json=payload,
            timeout=self.client._timeout,
        )

        if not response.ok:
            raise RuntimeError(
                f"LangSmith delete failed: status={response.status_code}, body={response.text}"
            )