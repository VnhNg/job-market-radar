from __future__ import annotations

import os
from dataclasses import dataclass

from langsmith import Client


@dataclass
class LangSmithRuntime:
    client: Client
    project_name: str | None = None

    @classmethod
    def open_default(cls) -> "LangSmithRuntime":
        return cls(
            client=Client(),
            project_name=os.getenv("LANGSMITH_PROJECT"),
        )

    def delete_thread(self, thread_id: str) -> None:
        if not thread_id.strip():
            raise ValueError("thread_id must be non-empty")
        if not self.project_name:
            raise RuntimeError(
                "LANGSMITH_PROJECT is not set; cannot safely scope trace deletion."
            )
        if not self.client.api_key:
            raise RuntimeError("LangSmith API key is not configured.")

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