from __future__ import annotations

from dataclasses import dataclass

from src.app.db import init_app_schema, open_app_db
from src.app.repos.thread_repo import ThreadRepo, ThreadRow
from src.app.repos.turn_repo import TurnRepo, TurnRow
from src.app.services.source_service import SourceCard, SourceService
from src.app.artifact_paths import APP_ARTIFACT_PATHS, EVAL_ARTIFACT_PATHS, ArtifactPaths
from src.assistant.modes.complete.bootstrap import (
    CompleteBootstrap,
    build_complete_bootstrap,
)
from src.assistant.modes.complete.graph.infra.checkpoints import (
    has_checkpoint,
    latest_checkpoint_id,
    thread_config,
)
from src.assistant.modes.complete.graph.infra.runtime_context import InvocationContext
from src.assistant.modes.complete.state import (
    ExecutionState,
    GraphState,
    SessionMemory,
    Turn,
    TurnContext,
    TurnMemory,
)


def _fresh_graph_state() -> GraphState:
    return GraphState(
        session=SessionMemory(tool_trace=[]),
        turn=Turn(
            context=TurnContext(question=""),
            memory=TurnMemory(tool_trace=[]),
            execution=ExecutionState(step_idx=0, calls=[]),
        ),
    )


def _title_from_first_question(thread_number: int, user_text: str, *, max_chars: int = 48) -> str:
    text = " ".join(user_text.strip().split())
    if not text:
        text = "new thread"
    text = text[:max_chars].rstrip()
    return f"{thread_number} · {text}"


@dataclass
class ChatService:
    bootstrap: CompleteBootstrap
    thread_repo: ThreadRepo
    turn_repo: TurnRepo
    source_service: SourceService

    @classmethod
    def open_with_artifact_paths(cls, artifact_paths: ArtifactPaths) -> "ChatService":
        conn = open_app_db(artifact_paths.db_path)
        init_app_schema(conn)
        bootstrap = build_complete_bootstrap(
            checkpoint_path=artifact_paths.checkpoint_path,
            langsmith_project=artifact_paths.langsmith_project,
        )
        thread_repo = ThreadRepo(conn)
        turn_repo = TurnRepo(conn)
        source_service = SourceService(
            bootstrap=bootstrap,
            turn_repo=turn_repo,
        )
        return cls(
            bootstrap=bootstrap,
            thread_repo=thread_repo,
            turn_repo=turn_repo,
            source_service=source_service,
        )

    @classmethod
    def open_app(cls) -> "ChatService":
        return cls.open_with_artifact_paths(APP_ARTIFACT_PATHS)

    @classmethod
    def open_eval(cls) -> "ChatService":
        return cls.open_with_artifact_paths(EVAL_ARTIFACT_PATHS)

    def close(self) -> None:
        self.bootstrap.checkpoint_runtime.close()
        self.thread_repo.conn.close()

    def list_threads(self) -> list[ThreadRow]:
        return self.thread_repo.list_threads()

    def get_thread(self, thread_id: str) -> ThreadRow | None:
        return self.thread_repo.get_thread(thread_id)
    
    def create_thread(self) -> ThreadRow:
        return self.thread_repo.create_thread(title="New Thread")
    
    def update_thread_title(self, *, thread_id: str, title: str) -> None:
        cleaned = title.strip()
        if not cleaned:
            raise ValueError("title must be non-empty")
        self.thread_repo.update_title(thread_id=thread_id, title=cleaned)
    
    def delete_thread(self, thread_id: str) -> None:
        if not thread_id.strip():
            raise ValueError("thread_id must be non-empty")

        self.bootstrap.langsmith_runtime.delete_thread(thread_id)
        self.bootstrap.checkpoint_runtime.delete_thread(thread_id)
        self.thread_repo.delete_thread(thread_id)

    def list_turns(self, *, thread_id: str) -> list[TurnRow]:
        return self.turn_repo.list_turns(thread_id=thread_id)

    def get_turn(self, turn_id: str) -> TurnRow | None:
        return self.turn_repo.get_turn(turn_id)

    def run_turn(
        self,
        *,
        thread_id: str,
        user_text: str,
        max_prior_user_questions: int,
        on_progress_event=None,
    ) -> tuple[TurnRow, InvocationContext]:
        if user_text is None:
            raise ValueError("user_text must not be None")
        user_text = user_text.strip()
        if not user_text:
            raise ValueError("user_text must not be empty")
        
        prior_user_questions = [
            turn.user_text
            for turn in self.turn_repo.list_turns(thread_id=thread_id)
        ]
        if max_prior_user_questions < 1:
            prior_user_questions = []
        else:
            prior_user_questions = prior_user_questions[-max_prior_user_questions:]
        
        graph = self.bootstrap.graph
        invoke_input = {} if has_checkpoint(graph, thread_id=thread_id) else _fresh_graph_state()
        ctx = InvocationContext(
            current_user_question=user_text,
            prior_user_questions=prior_user_questions,
            on_progress_event=on_progress_event,
        )

        with self.bootstrap.langsmith_runtime.trace_turn(
            thread_id=thread_id,
            user_question=user_text,
        ):
            graph.invoke(
                invoke_input,
                config=thread_config(thread_id),
                context=ctx,
            )

        if ctx.final_answer is None:
            raise RuntimeError("Invocation completed without final_answer")

        checkpoint_id = latest_checkpoint_id(graph, thread_id=thread_id)
        if checkpoint_id is None:
            raise RuntimeError("Invocation completed without checkpoint_id")

        turn = self.turn_repo.create_turn(
            thread_id=thread_id,
            user_text=user_text,
            assistant_text=ctx.final_answer,
            checkpoint_id=checkpoint_id,
        )

        if turn.position == 1:
            thread = self.thread_repo.get_thread(thread_id)
            if thread is None:
                raise RuntimeError(f"Thread not found after successful turn: {thread_id}")
            self.thread_repo.update_title(
                thread_id=thread_id,
                title=_title_from_first_question(thread.thread_number, user_text),
            )

        return turn, ctx
    

    def list_sources_for_turn(self, *, turn_id: str) -> list[SourceCard]:
        return self.source_service.list_sources_for_turn(turn_id=turn_id)
    

    def load_full_source_rows(self, *, turn_id: str, source_index: int) -> list[dict[str, object]]:
        return self.source_service.load_full_source_rows(
            turn_id=turn_id,
            source_index=source_index,
        )