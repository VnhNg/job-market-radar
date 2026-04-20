from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from queue import Empty, Queue

import streamlit as st

from src.app.services.chat_service import ChatService
from src.app.ui.session_state import (
    get_max_prior_user_questions,
    get_selected_thread_id,
    leave_new_chat_mode,
    set_selected_thread_id,
    store_turn_progress,
)


@dataclass
class RunResult:
    turn_id: str
    assistant_text: str
    progress_events: list[dict[str, object]] = field(default_factory=list)


@dataclass
class RunState:
    thread_id: str
    user_text: str
    future: Future
    progress_queue: Queue
    progress_events: list[dict[str, object]] = field(default_factory=list)
    status: str = "pending"
    error_message: str | None = None


def _get_executor() -> ThreadPoolExecutor:
    if "ui_executor" not in st.session_state:
        st.session_state.ui_executor = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="job-radar-ui",
        )
    return st.session_state.ui_executor


def active_runs() -> dict[str, RunState]:
    if "active_runs" not in st.session_state:
        st.session_state.active_runs = {}
    return st.session_state.active_runs


def get_active_run(thread_id: str | None) -> RunState | None:
    if not thread_id:
        return None
    return active_runs().get(thread_id)


def remove_failed_run(thread_id: str) -> None:
    run = get_active_run(thread_id)
    if run is not None and run.status == "failed":
        active_runs().pop(thread_id, None)


def _run_turn_worker(
    *,
    thread_id: str,
    user_text: str,
    max_prior_user_questions: int,
    progress_queue: Queue,
) -> RunResult:
    service = ChatService.open_default()
    captured_events: list[dict[str, object]] = []

    def on_progress_event(event: dict[str, object]) -> None:
        captured_events.append(event)
        progress_queue.put(event)

    try:
        turn, ctx = service.run_turn(
            thread_id=thread_id,
            user_text=user_text,
            max_prior_user_questions=max_prior_user_questions,
            on_progress_event=on_progress_event,
        )
        return RunResult(
            turn_id=turn.id,
            assistant_text=ctx.final_answer or "",
            progress_events=captured_events,
        )
    finally:
        service.close()


def _drain_run_progress(run: RunState) -> None:
    while True:
        try:
            event = run.progress_queue.get_nowait()
        except Empty:
            break
        run.progress_events.append(event)


def sync_active_runs() -> None:
    runs = active_runs()

    for thread_id, run in list(runs.items()):
        _drain_run_progress(run)

        if run.status != "pending":
            continue

        if not run.future.done():
            continue

        try:
            result = run.future.result()
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
            continue

        store_turn_progress(result.turn_id, result.progress_events)
        runs.pop(thread_id, None)


def ensure_thread_for_submit(svc: ChatService) -> str:
    thread_id = get_selected_thread_id()
    if thread_id:
        return thread_id

    thread = svc.create_thread()
    set_selected_thread_id(thread.id)
    leave_new_chat_mode()
    return thread.id


def submit_message(svc: ChatService, *, user_text: str) -> str:
    thread_id = ensure_thread_for_submit(svc)
    remove_failed_run(thread_id)

    active_run = get_active_run(thread_id)
    if active_run is not None and active_run.status == "pending":
        return thread_id

    progress_queue: Queue = Queue()
    future = _get_executor().submit(
        _run_turn_worker,
        thread_id=thread_id,
        user_text=user_text,
        max_prior_user_questions=get_max_prior_user_questions(),
        progress_queue=progress_queue,
    )

    active_runs()[thread_id] = RunState(
        thread_id=thread_id,
        user_text=user_text,
        future=future,
        progress_queue=progress_queue,
    )
    return thread_id